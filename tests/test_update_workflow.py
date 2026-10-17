import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('updater', ROOT / 'scripts/update_workflow.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def legacy():
    # Minimal original branch plus a user-customized unrelated node and settings.
    template = json.loads(updater.TEMPLATE.read_text())
    serper = copy.deepcopy(next(n for n in template['nodes'] if n['name'] == 'Search Web (Serper)'))
    serper.update(name='Search Web', id='saved-search-id')
    formatter = copy.deepcopy(next(n for n in template['nodes'] if n['name'] == 'Format Search Results'))
    formatter['parameters']['jsCode'] = formatter['parameters']['jsCode'].replace('Search Web (Serper)', 'Search Web')
    return {'name': 'My customized assistant', 'id': 'saved-workflow', 'active': False,
            'settings': {'callerPolicy': 'none', 'executionTimeout': 90},
            'nodes': [serper, formatter, {'id': 'route', 'name': 'Route by Intent', 'type': 'n8n-nodes-base.switch', 'parameters': {}},
                      {'id': 'summary', 'name': 'Summarize (Groq)', 'type': 'n8n-nodes-base.httpRequest', 'parameters': {'jsonBody': 'my custom model and prompt'}},
                      *[copy.deepcopy(n) for n in template['nodes'] if n['name'] in ('Respond to Webhook', 'Parse Intent', 'Voice Agent Webhook', 'Final Query')],
                      {'id': 'custom', 'name': 'Custom integration', 'credentials': {'example': {'id': 'saved'}}}],
            'connections': {source: {'main': [updater.edge(destination)]}
                            for source, destination in [('Route by Intent', 'Search Web'),
                                                        ('Search Web', 'Format Search Results'),
                                                        ('Format Search Results', 'Summarize (Groq)')]}}


class UpdateWorkflowTests(unittest.TestCase):
    def test_preserves_credentials_disabled_identity_and_unrelated_settings(self):
        old = legacy()
        search = old['nodes'][0]
        search.update(disabled=True, credentials={'httpHeaderAuth': {'id': 'my-secret-reference'}})
        search['parameters'].update(specifyHeaders='json', jsonHeaders='={{ {"X-API-KEY": $env.SERPER_API_KEY} }}')
        saved = copy.deepcopy(old)
        result = updater.upgrade(old)
        nodes = {n['name']: n for n in result['nodes']}
        self.assertEqual(old, saved)
        self.assertEqual(result['settings'], old['settings'])
        self.assertEqual(nodes['Search Web']['id'], 'saved-search-id')
        self.assertTrue(nodes['Search Web']['disabled'])
        self.assertEqual(nodes['Search Web (Serper)']['parameters'], search['parameters'])
        self.assertEqual(nodes['Search Web (Serper)']['credentials'], search['credentials'])
        self.assertEqual(nodes['Custom integration'], old['nodes'][-1])
        self.assertEqual(nodes['Summarize (Groq)']['parameters']['jsonBody'], 'my custom model and prompt')
        self.assertEqual(result['connections']['Search Web']['main'][0], updater.edge('Check Research Permission'))

    def test_rejects_rewired_custom_and_already_updated_workflows(self):
        for change in [
            lambda w: w['connections']['Route by Intent']['main'][0].append({'node': 'Custom integration', 'type': 'main', 'index': 0}),
            lambda w: w['nodes'][1]['parameters'].update(jsCode='custom formatter'),
            lambda w: w['nodes'].append({'name': 'Search Web (Parallel)', 'id': 'custom-parallel'}),
        ]:
            value = legacy()
            change(value)
            with self.assertRaises(ValueError):
                updater.upgrade(value)

    def test_rejects_custom_references_to_old_search_output(self):
        for expression in ['$node["Search Web"].json.organic', "$('Search Web').first().json", "$items('Search Web')"]:
            value = legacy()
            value['nodes'][3]['parameters']['jsonBody'] = expression
            with self.assertRaisesRegex(ValueError, 'Additional Search Web reference'):
                updater.upgrade(value)

    def test_does_not_restore_removed_unrelated_nodes(self):
        result = updater.upgrade(legacy())
        names = {node['name'] for node in result['nodes']}
        self.assertNotIn('Error Trigger', names)
        self.assertNotIn('Groq Whisper STT', names)
        self.assertNotIn('Fetch Weather', names)
        self.assertIn('Custom integration', names)
        self.assertIn('Search Web (Parallel)', names)

    def test_refuses_missing_or_renamed_fixed_dependencies(self):
        for name in ('Respond to Webhook', 'Parse Intent', 'Voice Agent Webhook', 'Final Query'):
            for rename in (False, True):
                value = legacy()
                target = next(n for n in value['nodes'] if n['name'] == name)
                if rename:
                    target['name'] = 'My ' + name
                else:
                    value['nodes'].remove(target)
                with self.subTest(name=name, rename=rename):
                    with self.assertRaisesRegex(ValueError, 'Required research dependency'):
                        updater.upgrade(value)

    def test_refuses_incompatible_dependencies_and_introduces_no_dangling_edges(self):
        value = legacy()
        next(n for n in value['nodes'] if n['name'] == 'Respond to Webhook')['type'] = 'custom.responder'
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            updater.upgrade(value)
        result = updater.upgrade(legacy())
        names = {n['name'] for n in result['nodes']}
        for outputs in result['connections'].values():
            for branches in outputs.values():
                for branch in branches:
                    for connection in branch:
                        self.assertIn(connection['node'], names)

    def test_cli_writes_separate_output_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'export.json'
            source.write_text(json.dumps(legacy()))
            original = source.read_bytes()
            command = [sys.executable, str(ROOT / 'scripts/update_workflow.py'), str(source)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            output = source.with_name('export.parallel.json')
            self.assertTrue(output.is_file())
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 1)
            self.assertEqual(source.read_bytes(), original)
            same = subprocess.run(command + [str(source)], capture_output=True, text=True)
            self.assertEqual(same.returncode, 1)
            self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
