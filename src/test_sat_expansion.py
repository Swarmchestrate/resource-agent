"""Count expansion tests; cloud and YAML dependencies are not required."""

import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import sys
import types

from sat_expansion import expand_sat_counts


def microservice(count=1):
    return {'type': 'swch:Microservice', 'properties': {'replicas': 2},
            'requirements': [{'host': {'count': count, 'node_filter': {'cpu': 2}}}]}


def example(count=3):
    return {'service_template': {
        'node_templates': {'details': microservice(count),
                           'frontend': microservice(count),
                           'ratings': microservice(),
                           'banner': {'type': 'swch:File'}},
        'policies': [{'frontend_colocation': {
            'type': 'swch:Scheduling.Colocation', 'targets': ['details', 'frontend']}}]}}


def agent_class():
    tree = ast.parse(Path(__file__).with_name('ra_base.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'ResourceAgent')
    names = {'_get_cluster_name', '_process_job_requirements', '_get_independent_microservices',
             '_find_valid_combinations', '_get_instance_node_labels',
             '_handle_create_lead_resource', '_handle_create_resource_blocking'}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in names]
    # JSON is a YAML subset; use it to exercise file plumbing without PyYAML.
    def write_yaml(data, filename):
        Path(filename).write_text(json.dumps(data))
    scope = {'expand_sat_counts': expand_sat_counts, 'Path': Path, 'json': json,
             'yaml': types.SimpleNamespace(safe_load=json.load, dump=json.dumps),
             'write_yaml': write_yaml, 'time': Mock()}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'ra_base.py', 'exec'), scope)
    return scope['ResourceAgent']


class ExpansionTests(unittest.TestCase):
    def test_labels_restore_only_known_instances_and_preserve_other_labels(self):
        agent = agent_class()()
        scope = agent._get_instance_node_labels.__globals__
        key = 'labels.swarmchestrate.eu/ms_id'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'KB').mkdir()
            (root / 'KB/tosca_job.instances.json').write_text(json.dumps({
                'audio-class-2': 'audio-class', 'frontend-10': 'frontend',
                'service-2': 'service-2'}))
            scope['Path'] = lambda value: root / value
            for instance, expected in [('audio-class-2', 'audio-class'),
                                       ('frontend-10', 'frontend'),
                                       ('service-2', 'service-2'), ('unknown-3', 'unknown-3')]:
                info = {'node_labels': {key: instance, 'zone': 'uk'}}
                original = deepcopy(info)
                self.assertEqual(agent._get_instance_node_labels('job', info),
                                 {key: expected, 'zone': 'uk'})
                self.assertEqual(info, original)
            self.assertEqual(agent._get_instance_node_labels('missing', info), info['node_labels'])
            self.assertEqual(agent._get_instance_node_labels('job', {}), {})

    def test_builder_receives_original_label_and_unique_name_for_both_roles(self):
        class BuilderReached(Exception):
            pass

        key = 'labels.swarmchestrate.eu/ms_id'
        for role in ('master', 'worker'):
            for provider in ('aws', 'openstack', 'edge'):
                with self.subTest(role=role, provider=provider):
                    agent = agent_class()()
                    agent.ra_id = 'ra'
                    agent.logger = Mock()
                    agent.deleted_jobs = set()
                    agent.pending_deletions = {}
                    agent.job_capreg_allocated = {}
                    agent.capacity_file = 'capacity.yaml'
                    agent.dry_run = False
                    scope = agent._get_instance_node_labels.__globals__
                    info = {'node_labels': {key: 'audio-class-2', 'zone': 'uk'}}
                    scope['Sardou'] = Mock()
                    scope['Sardou'].return_value.get_cluster.return_value = {'node': info}
                    scope['_os'] = Mock()
                    scope['_os'].getenv.return_value = 'true'
                    builder = Mock()
                    builder.return_value.add_node.side_effect = BuilderReached
                    scope['Swarmchestrate'] = builder
                    offer = {'offer': {'ids': {'ms_id': 'audio-class-2', 'offer_id': 'offer',
                                              'res_type': 'edge' if provider == 'edge' else 'cloud',
                                              'provider_id': provider}}}
                    message = {'job_id': 'ra-aws-job', 'lead_resource': role == 'master',
                               'leader_resource_name': 'audio-class-2',
                               'offer_info': {'audio-class-2': offer},
                               'instance': {'node-name': 'audio-class-2', 'k3s_role': role,
                                            'resource': offer},
                               'master_info': {'cluster_name': 'ra_aws_job', 'master_ip': 'ip', 'k3s_token': 'token'}}
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        (root / 'KB').mkdir()
                        (root / 'KB/tosca_ra-aws-job.instances.json').write_text(
                            json.dumps({'audio-class-2': 'audio-class'}))
                        scope['Path'] = lambda value: root / value
                        handler = (agent._handle_create_lead_resource if role == 'master'
                                   else agent._handle_create_resource_blocking)
                        with patch('builtins.print'), self.assertRaises(BuilderReached):
                            handler('hub', message)
                    config = builder.return_value.add_node.call_args.args[0]
                    self.assertEqual(config['cluster_name'], 'ra_aws_job')
                    self.assertEqual(config['resource_name'], 'audio-class-2')
                    self.assertEqual(config['node_labels'], [f'{key}=audio-class', 'zone=uk'])

    def test_expansion_preserves_original_and_pairs_colocation(self):
        source = example()
        before = deepcopy(source)
        expanded, origins = expand_sat_counts(source)
        nodes = expanded['service_template']['node_templates']
        self.assertEqual(source, before)
        self.assertEqual(set(nodes), {'details-1', 'details-2', 'details-3',
                                     'frontend-1', 'frontend-2', 'frontend-3',
                                     'ratings', 'banner'})
        for instance, original in origins.items():
            self.assertEqual(nodes[instance]['requirements'][0]['host']['count'], 1)
            self.assertEqual(nodes[instance]['properties']['replicas'], 2)
            self.assertEqual(nodes[instance]['requirements'][0]['host']['node_filter'], {'cpu': 2})
            self.assertIn(original, before['service_template']['node_templates'])
        policies = expanded['service_template']['policies']
        self.assertEqual([next(iter(p.values()))['targets'] for p in policies],
                         [[f'details-{i}', f'frontend-{i}'] for i in range(1, 4)])
        self.assertEqual(expand_sat_counts(source), (expanded, origins))

    def test_default_count_and_non_host_requirements(self):
        source = example(1)
        node = source['service_template']['node_templates']['details']
        del node['requirements'][0]['host']['count']
        node['requirements'].append({'volume': {'node': 'banner'}})
        expanded, origins = expand_sat_counts(source)
        self.assertEqual(origins['details'], 'details')
        self.assertEqual(expanded['service_template']['node_templates']['details']['requirements'],
                         [{'host': {'count': 1, 'node_filter': {'cpu': 2}}},
                          {'volume': {'node': 'banner'}}])

    def test_invalid_counts(self):
        for count in (0, -1, True, 1.5, '3', None):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'positive integer'):
                expand_sat_counts(example(count))

    def test_unequal_colocation_counts(self):
        source = example()
        source['service_template']['node_templates']['frontend'] = microservice(2)
        with self.assertRaisesRegex(ValueError, 'equal host counts'):
            expand_sat_counts(source)

    def test_node_and_policy_collisions(self):
        source = example()
        source['service_template']['node_templates']['details-1'] = microservice()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            expand_sat_counts(source)
        source = example()
        source['service_template']['policies'].append({'frontend_colocation-1': {}})
        with self.assertRaisesRegex(ValueError, 'already exists'):
            expand_sat_counts(source)

    def test_generated_name_length(self):
        source = {'service_template': {'node_templates': {'a' * 63: microservice(2)}}}
        with self.assertRaisesRegex(ValueError, 'exceeds 63'):
            expand_sat_counts(source)

    def test_offer_generation_uses_expanded_copy_and_saves_mapping(self):
        agent = agent_class()()
        agent.logger = Mock()
        agent.ra_id = 'ra'
        agent.capacity = {'metadata': {}}
        agent.capreg = Mock()
        agent.capreg.resource_offer_generate_from_SAT_file.return_value = {}
        agent.peer = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sat.yaml'
            path.write_text(json.dumps(example()))
            original = path.read_text()
            agent._process_job_requirements('job', 'client', str(path), 'hub')
            matching = path.with_name('sat.expanded.yaml')
            agent.capreg.resource_offer_generate_from_SAT_file.assert_called_once_with('job', str(matching))
            self.assertEqual(path.read_text(), original)
            self.assertIn('details-3', json.loads(matching.read_text())['service_template']['node_templates'])
            self.assertEqual(json.loads(path.with_name('sat.instances.json').read_text())['details-3'], 'details')

    def test_combinations_require_every_expanded_independent_instance(self):
        agent = agent_class()()
        yaml_module = types.ModuleType('ruamel.yaml')
        yaml_module.YAML = lambda **kwargs: types.SimpleNamespace(load=json.load)
        ruamel = types.ModuleType('ruamel')
        ruamel.yaml = yaml_module
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                sys.modules, {'ruamel': ruamel, 'ruamel.yaml': yaml_module}):
            path = Path(directory) / 'sat.yaml'
            path.write_text(json.dumps(example()))
            resources = agent._get_independent_microservices(str(path))
        self.assertEqual(resources, ['details-1', 'details-2', 'details-3', 'ratings'])
        offers = {'ra': {name: {f'offer-{name}': {'ids': {'ms_id': name}}}
                         for name in resources}}
        combinations = agent._find_valid_combinations(offers, resources)
        self.assertEqual(set(combinations['combination_1']), set(resources))
        del offers['ra']['details-3']
        self.assertEqual(agent._find_valid_combinations(offers, resources), {})


if __name__ == '__main__':
    unittest.main()
