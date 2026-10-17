#!/usr/bin/env python3
"""Add Parallel research to an exported workflow without dropping saved settings."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / 'Voice-AI-Research-Assistant.json'


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


# Only repair unchanged original expressions; preserve user-edited prompts/models.
ORIGINAL_EXPRESSIONS = {'Final Query': {'jsCode': 'b6c66f1655907da0644d82a60dd2f6d8917e72e1ee9b6e3b681a2c585dbe43de'}, 'Classify Intent (Groq)': {'jsonBody': 'e3e8d1eeae3580aa5a3297f9730acc884bf182277ef3fc6202d965a250fdaa6b'}, 'Format Search Results': {'jsCode': 'f14d6dc9047e7d152a6d8341fadc7ca97eab4b49ac923c806505409cad342137'}, 'Summarize (Groq)': {'jsonBody': '72e37c630d4204d5e442800f0bd35698261dab2a7155e980bd07cdf8cc2ecefd'}, 'Respond to Webhook': {'responseBody': '2141bf3a7fed8cb369ecec5284ced4c991074fcf0878693cbbe7e1e912b2e9ba'}}


def edge(name):
    return [{'node': name, 'type': 'main', 'index': 0}]


def upgrade(existing, template=None):
    template = template or json.loads(TEMPLATE.read_text())
    if not isinstance(existing, dict) or not isinstance(existing.get('nodes'), list):
        raise ValueError('Expected one exported workflow object.')
    old_nodes = {node['name']: node for node in existing['nodes']}
    if len(old_nodes) != len(existing['nodes']):
        raise ValueError('Duplicate node names are unsupported.')
    for name in ('Search Web', 'Format Search Results', 'Route by Intent', 'Summarize (Groq)'):
        if name not in old_nodes:
            raise ValueError('Required research node is missing: ' + name)
    search = old_nodes['Search Web']
    if search['type'] != 'n8n-nodes-base.httpRequest':
        raise ValueError('Search Web must be the original Serper HTTP node.')
    connections = existing.get('connections', {})
    expected = {'Route by Intent': 'Search Web', 'Search Web': 'Format Search Results',
                'Format Search Results': 'Summarize (Groq)'}
    for source, destination in expected.items():
        outputs = connections.get(source, {}).get('main', [])
        if not outputs or outputs[0] != edge(destination):
            raise ValueError('Unsupported research rewiring at ' + source)
        if source != 'Route by Intent' and (len(outputs) != 1 or set(connections[source]) != {'main'}):
            raise ValueError('Unsupported additional research outputs at ' + source)
    for source, value in connections.items():
        for kind, branches in value.items():
            for outputs in branches:
                for connection in outputs:
                    allowed = {'Search Web': 'Route by Intent', 'Format Search Results': 'Search Web'}
                    if connection['node'] in allowed and (kind != 'main' or source != allowed[connection['node']]):
                        raise ValueError('Unsupported additional research input from ' + source)
    formatter = old_nodes['Format Search Results']['parameters'].get('jsCode', '')
    if fingerprint(formatter) != ORIGINAL_EXPRESSIONS['Format Search Results']['jsCode']:
        raise ValueError('Custom search formatter: adapt the research branch manually.')
    fresh_nodes = {node['name']: node for node in template['nodes']}
    additions = [node for node in template['nodes'] if node['name'] not in old_nodes]
    # An existing new-provider name could hide a custom integration. Never overwrite it.
    new_names = {'Search Web (Serper)', 'Route Search Provider', 'Initialize Parallel MCP',
                 'Check MCP Initialization', 'Notify Parallel MCP', 'Search Web (Parallel)',
                 'Format Parallel Results', 'Research Has Results?', 'Check Research Permission'}
    if new_names.intersection(old_nodes):
        raise ValueError('Workflow already has provider nodes; update it manually.')
    result = copy.deepcopy(existing)
    nodes = {node['name']: node for node in result['nodes']}
    gateway = copy.deepcopy(fresh_nodes['Search Web'])
    gateway['id'] = search['id']
    for field in ('disabled', 'position', 'notes', 'notesInFlow'):
        if field in search:
            gateway[field] = copy.deepcopy(search[field])
    result['nodes'][result['nodes'].index(nodes['Search Web'])] = gateway
    nodes['Search Web'] = gateway
    result['nodes'].extend(copy.deepcopy(additions))
    nodes = {node['name']: node for node in result['nodes']}
    serper = nodes['Search Web (Serper)']
    # Keep the complete native request configuration, including expressions and credentials.
    for field, value in search.items():
        if field not in ('id', 'name', 'position', 'disabled'):
            serper[field] = copy.deepcopy(value)
    ids = [node['id'] for node in result['nodes']]
    if len(ids) != len(set(ids)):
        raise ValueError('New node IDs conflict with existing workflow nodes.')
    nodes['Format Search Results']['parameters']['jsCode'] = fresh_nodes['Format Search Results']['parameters']['jsCode']
    for name, fields in ORIGINAL_EXPRESSIONS.items():
        if name == 'Format Search Results' or name not in nodes:
            continue
        for field, digest in fields.items():
            value = nodes[name]['parameters'].get(field)
            if isinstance(value, str) and fingerprint(value) == digest:
                nodes[name]['parameters'][field] = fresh_nodes[name]['parameters'][field]
    for source in ('Search Web', 'Format Search Results', *sorted(new_names)):
        if source in template['connections']:
            result['connections'][source] = copy.deepcopy(template['connections'][source])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('output', type=Path, nargs='?')
    args = parser.parse_args()
    output = args.output or args.export.with_name(args.export.stem + '.parallel.json')
    try:
        updated = upgrade(json.loads(args.export.read_text()))
        # Exclusive creation also protects the input and any existing output file.
        with output.open('x') as stream:
            stream.write(json.dumps(updated, indent=2, ensure_ascii=False) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Cannot update workflow: {error}\n')
    print(f'Updated workflow written to {output}')


if __name__ == '__main__':
    main()
