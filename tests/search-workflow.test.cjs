// Behavior tests for the JavaScript embedded in the importable n8n workflow.
// Run with: node --test tests/search-workflow.test.cjs
// Native n8n engine/caller validation is separate from these isolated tests.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const workflow = JSON.parse(fs.readFileSync(`${__dirname}/../Voice-AI-Research-Assistant.json`, 'utf8'));
const node = name => workflow.nodes.find(n => n.name === name);
function code(name, input, body = {}, change = s => s, serper = {}) {
  const nodes = {
    'Voice Agent Webhook': { json: { body } },
    'Search Web (Serper)': { parameter: { ...node('Search Web (Serper)').parameters, ...serper } },
  };
  return JSON.parse(JSON.stringify(vm.runInNewContext(`(function() { ${change(node(name).parameters.jsCode)} })()`, {
    $node: nodes, $input: { first: () => ({ json: input }) },
  })));
}
const choose = (body, change, serper) => code('Search Web', { query: 'n8n releases', language: 'en' }, body, change, serper);
const format = result => code('Format Parallel Results', { body: JSON.stringify({ jsonrpc: '2.0', id: 2, result }) });
test('fresh installation uses Parallel; configured Serper keeps its selection', () => {
  assert.equal(choose({}).search_provider, 'parallel');
  assert.equal(choose({}, undefined, { headerParameters: { parameters: [{ name: 'X-API-KEY', value: 'saved-key' }] } }).search_provider, 'serper');
  assert.equal(choose({}, undefined, { authentication: 'genericCredentialType' }).search_provider, 'serper');
});
test('stored choices and explicit overrides are respected', () => {
  assert.equal(choose({}, s => s.replace("provider = 'auto'", "provider = 'serper'")).search_provider, 'serper');
  assert.equal(choose({ search_provider: 'serper' }).search_provider, 'serper');
  assert.equal(choose({ search_provider: 'parallel' }, undefined, { authentication: 'genericCredentialType' }).search_provider, 'parallel');
});
test('disable controls win over overrides and unknown providers fail closed', () => {
  for (const value of [
    choose({ search_provider: 'parallel' }, s => s.replace('enabled = true', 'enabled = false')),
    choose({ search_provider: 'parallel' }, s => s.replace("provider = 'auto'", "provider = 'disabled'")),
    choose({ search_enabled: false, search_provider: 'parallel' }),
    choose({ search_provider: 'disabled' }),
    choose({ search_provider: 'unexpected' }),
  ]) { assert.equal(value.search_provider, 'disabled'); assert.equal(value.error, true); }
});
test('results retain source URLs and excerpts in the existing summary contract', () => {
  assert.deepEqual(format({ structuredContent: { results: [{ title: 'Release notes', url: 'https://example.com/a?x=1&y=2', excerpts: ['First', 'Second'] }] } }), {
    results: [{ title: 'Release notes', url: 'https://example.com/a?x=1&y=2', snippet: 'First\nSecond' }],
  });
  assert.equal(format({ content: [{ type: 'text', text: JSON.stringify({ results: [{ url: 'https://example.org', excerpts: ['Content'] }] }) }] }).results[0].title, 'https://example.org');
});
test('JSON and SSE responses are supported; malformed/error/empty results fail closed', () => {
  const result = { content: [{ type: 'text', text: JSON.stringify({ results: [{ url: 'https://example.org', excerpts: ['Content'] }] }) }] };
  const sse = `: keepalive\n\nevent: message\ndata: ${JSON.stringify({ jsonrpc: '2.0', id: 2, result })}\n\n`;
  assert.equal(code('Format Parallel Results', { body: sse }).results[0].url, 'https://example.org');
  for (const input of [
    { error: 'timeout' }, { body: 'invalid' }, { body: JSON.stringify({ id: 2, error: { message: 'bad request' } }) },
    { body: JSON.stringify({ id: 2, result: { isError: true, content: [{ type: 'text', text: 'quota' }] } }) },
    { body: JSON.stringify({ id: 3, result }) },
    { body: JSON.stringify({ id: 2, result: { structuredContent: { results: [] } } }) },
    { body: JSON.stringify({ id: 2, result: { structuredContent: { results: [{ url: 'javascript:alert(1)' }] } } }) },
  ]) assert.equal(code('Format Parallel Results', input).error, true);
});
test('handshake accepts negotiated sessions and rejects failed initialization', () => {
  assert.deepEqual(code('Check MCP Initialization', { body: JSON.stringify({ id: 1, result: { protocolVersion: '2025-03-26', capabilities: { tools: {} } } }), headers: { 'mcp-session-id': 'session' } }), { protocolVersion: '2025-03-26', sessionId: 'session' });
  assert.throws(() => code('Check MCP Initialization', { body: JSON.stringify({ id: 1, error: { message: 'denied' } }) }), /initialization failed/);
});
test('research results feed the guarded consumer and configured Serper stays intact', () => {
  assert.equal(workflow.connections['Route by Intent'].main[0][0].node, 'Search Web');
  assert.equal(workflow.connections['Search Web'].main[0][0].node, 'Check Research Permission');
  assert.equal(workflow.connections['Route Search Provider'].main[1][0].node, 'Search Web (Serper)');
  assert.equal(workflow.connections['Format Parallel Results'].main[0][0].node, 'Research Has Results?');
  assert.equal(workflow.connections['Research Has Results?'].main[0][0].node, 'Summarize (Groq)');
  assert.equal(workflow.connections['Research Has Results?'].main[1][0].node, 'Respond to Webhook');
  assert.equal(node('Search Web (Serper)').parameters.url, 'https://google.serper.dev/search');
});

test('active JSON header mode preserves configured Serper without using stale hidden fields', () => {
  assert.equal(choose({}, undefined, { specifyHeaders: 'json', jsonHeaders: '{"X-API-KEY":"json-key"}' }).search_provider, 'serper');
  assert.equal(choose({}, undefined, { specifyHeaders: 'json', jsonHeaders: '{}', headerParameters: { parameters: [{ name: 'X-API-KEY', value: 'stale-key' }] } }).search_provider, 'parallel');
  assert.equal(choose({}, undefined, { specifyHeaders: 'json', jsonHeaders: 'invalid' }).search_provider, 'serper');
});
test('a disabled gateway passing input cannot authorize research', () => {
  const denied = code('Check Research Permission', { query: 'n8n releases', intent: 'research' });
  assert.equal(denied.error, true); assert.equal(denied.search_provider, 'disabled');
  const allowed = choose({});
  assert.equal(code('Check Research Permission', allowed).search_provider, 'parallel');
});
