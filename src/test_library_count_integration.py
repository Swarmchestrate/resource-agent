"""Integration contract for Sardou count extraction and swchcapreg offers."""

import unittest

try:
    from sardou.requirements import tosca_to_ask_dict
    from swch_capreg import SwChCapacityRegistry
except ImportError:  # The ordinary lightweight unit-test environment omits these libs.
    tosca_to_ask_dict = None
    SwChCapacityRegistry = None

from test_sat_expansion import agent_class


@unittest.skipUnless(SwChCapacityRegistry, "Sardou and swchcapreg are not installed")
class LibraryCountIntegrationTests(unittest.TestCase):
    def test_count_three_becomes_one_atomic_offer_and_three_node_slots(self):
        sat = {'service_template': {'node_templates': {'audio-class': {
            'type': 'swch:Microservice',
            'requirements': [{'host': {
                'count': 3,
                'node_filter': {'$and': [{'$greater_or_equal': [
                    {'$get_property': ['SELF', 'TARGET', 'CAPABILITY',
                                      'host', 'num-cpus']}, 2]}]}}}]}}}}
        requirements = tosca_to_ask_dict(sat)
        self.assertEqual(requirements['audio-class']['count'], 3)

        registry = SwChCapacityRegistry('ra-test')
        registry.initialize({
            'cloud_flavours': {'small': {
                'resource': {'provider': 'test-cloud'},
                'host': {'num-cpus': 2, 'mem-size': 4, 'disk-size': 10,
                         'bandwidth': 100},
                'pricing': {'cost': 1},
                'energy': {'consumption': 1}}},
            'cloud_capacity_flavour': {'small': 3}})
        registry.extract_application_requirements_from_SAT_file = lambda _: requirements

        offers = registry.resource_offer_generate_from_SAT_file('app', 'sat.yaml')
        registry_offer_id, aggregate = next(iter(offers['audio-class'].items()))
        self.assertEqual(len(aggregate), 3)
        self.assertEqual({item['ids']['ms_id'] for item in aggregate}, {'audio-class'})
        self.assertEqual(len({item['ids']['offer_id'] for item in aggregate}), 3)

        agent = agent_class()()
        combinations = agent._find_valid_combinations(
            {'ra-test': offers}, ['audio-class'])
        allocation = combinations['combination_1']
        self.assertEqual(set(allocation),
                         {'audio-class-1', 'audio-class-2', 'audio-class-3'})
        for node_offer in allocation.values():
            instance = next(iter(node_offer.values()))
            self.assertEqual(instance['ids']['ms_id'], 'audio-class')
            self.assertEqual(instance['ids']['registry_offer_id'], registry_offer_id)

        self.assertTrue(registry.resource_offer_accept(registry_offer_id, aggregate))
        state = registry.resource_set_query_all('app', 'audio-class')
        self.assertEqual(state['cloud']['small']['assigned'], 3)
        for node_offer in allocation.values():
            instance_id, instance = next(iter(node_offer.items()))
            resource_set = registry.resource_set_get_from_offer(instance_id, instance)
            registry.resource_set_deployed(
                'app', 'audio-class', resource_set['restype'],
                resource_set['resid'], resource_set['count'])
        state = registry.resource_set_query_all('app', 'audio-class')
        self.assertEqual(state['cloud']['small']['allocated'], 3)


if __name__ == '__main__':
    unittest.main()
