"""Isolated deletion protocol tests; deployment dependencies are not required."""
import ast
from pathlib import Path
import threading
import unittest
from typing import Any, Dict
from unittest.mock import Mock


def load_agent_class():
    # Compile the actual handlers without importing cloud/P2P dependencies.
    tree = ast.parse(Path(__file__).with_name('ra_base.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'ResourceAgent')
    names = {'_get_cluster_name', '_clear_job_data', '_handle_delete_job_broadcast',
             '_handle_delete_job_ack', '_start_job_deletion',
             '_handle_job_delete', '_handle_job_delete_all',
             '_handle_resource_response', '_handle_create_resource_blocking'}
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in names]
    scope = {'Dict': Dict, 'Any': Any, 'Swarmchestrate': Mock(), 'threading': Mock()}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'ra_base.py', 'exec'), scope)
    return scope['ResourceAgent'], scope['Swarmchestrate']


class DeletionTests(unittest.TestCase):
    def setUp(self):
        cls, self.builder = load_agent_class()
        self.agent = cls()
        a = self.agent
        a.ra_id = 'hub'
        a.peer = Mock(peer_id='hub')
        a.peer.find_peers.return_value = ['worker', 'worker']
        a.logger = Mock()
        a.capreg = Mock()
        a.resource_lock = threading.Lock()
        a.dry_run = False
        a.deletion_lock = threading.RLock()
        a.config = {}
        a.pending_deletions = {}
        a.deleted_jobs = set()
        for name in ('job_states', 'job_responses', 'master_info', 'job_clients',
                     'job_offers', 'lead_resource', 'job_capreg_allocated',
                     'job_tosca', 'tosca'):
            setattr(a, name, {})
        self.add_job('job')

    def add_job(self, job):
        self.agent.job_states[job] = {'state': 'Running'}
        self.agent.job_clients[job] = 'original-submitter'
        self.agent.job_tosca[job] = {}

    def replies(self, kind='MSG_DELETE_RESPONSE'):
        return [call.args for call in self.agent.peer.send.call_args_list
                if call.args[1] == kind]

    def ack(self, job='job', result='success'):
        self.agent._handle_delete_job_ack('worker', {
            'job_id': job, 'result': result, 'message': 'release error',
        })

    def test_waits_for_ack_and_replies_to_requester(self):
        self.agent._handle_job_delete('requester', {'job_id': 'job'})
        self.assertEqual(self.replies(), [])
        self.agent.capreg.resources_and_offers_destroy_all.assert_called_once_with('job')
        self.assertEqual(len(self.replies('MSG_DELETE_JOB_BROADCAST')), 1)
        self.ack()
        self.assertEqual(self.replies()[0][0], 'requester')
        self.assertEqual(self.replies()[0][2]['result'], 'success')
        self.assertNotIn('job', self.agent.job_tosca)
        self.ack()
        self.assertEqual(len(self.replies()), 1)

    def test_cleanup_failure_is_reported_and_routing_retained(self):
        self.agent._handle_job_delete('requester', {'job_id': 'job'})
        self.ack(result='failure')
        self.assertEqual(self.replies()[0][2]['result'], 'failure')
        self.assertIn('job', self.agent.job_clients)

    def test_missing_ack_times_out(self):
        self.agent._handle_job_delete('requester', {'job_id': 'job'})
        scope = self.agent._start_job_deletion.__globals__
        expire = scope['threading'].Timer.call_args.args[1]
        expire()
        self.assertEqual(self.replies()[0][2]['result'], 'failure')
        self.assertIn('Timed out', self.replies()[0][2]['message'])
        self.assertNotIn('job', self.agent.pending_deletions)

    def test_unknown_job_replies_without_broadcast(self):
        self.agent._handle_job_delete('requester', {'job_id': 'missing'})
        self.assertEqual(self.replies()[0][2]['result'], 'failure')
        self.assertEqual(self.replies('MSG_DELETE_JOB_BROADCAST'), [])

    def test_duplicate_broadcast_releases_once(self):
        payload = {'job_id': 'job', 'LR_id': 'hub'}
        self.agent._handle_delete_job_broadcast('remote-hub', payload)
        self.agent._handle_delete_job_broadcast('remote-hub', payload)
        self.builder.return_value.destroy.assert_called_once()
        self.agent.capreg.resources_and_offers_destroy_all.assert_called_once()
        self.assertEqual(len(self.replies('MSG_DELETE_JOB_ACK')), 2)

    def test_delete_uses_cluster_name_but_releases_capacity_by_job_id(self):
        job = 'ra-aws-20260916-163725'
        self.add_job(job)
        self.agent._handle_delete_job_broadcast('remote-hub', {'job_id': job, 'LR_id': 'hub'})
        self.builder.return_value.destroy.assert_called_once_with(
            'ra_aws_20260916_163725', dryrun=False)
        self.agent.capreg.resources_and_offers_destroy_all.assert_called_once_with(job)

    def test_destroy_failure_preserves_capacity_and_state(self):
        self.builder.return_value.destroy.side_effect = RuntimeError('destroy failed')
        self.agent._handle_delete_job_broadcast('remote-hub', {'job_id': 'job', 'LR_id': 'hub'})
        self.agent.capreg.resources_and_offers_destroy_all.assert_not_called()
        self.assertIn('job', self.agent.job_states)
        self.assertEqual(self.replies('MSG_DELETE_JOB_ACK')[0][2]['result'], 'failure')

    def test_delete_all_finishes_in_ack_order(self):
        self.add_job('second')
        self.agent._handle_job_delete_all('requester', {})
        self.assertEqual(self.replies('MSG_DELETE_ALL_RESPONSE'), [])
        self.ack('second', result='failure')
        self.assertFalse(self.replies('MSG_DELETE_ALL_RESPONSE')[0][2]['last_job'])
        self.ack()
        self.assertTrue(self.replies('MSG_DELETE_ALL_RESPONSE')[-1][2]['last_job'])

    def test_empty_delete_all_replies(self):
        self.agent._clear_job_data('job')
        self.agent._handle_job_delete_all('requester', {})
        self.assertTrue(self.replies('MSG_DELETE_ALL_RESPONSE')[0][2]['last_job'])

    def test_late_messages_do_not_recreate_deleted_job(self):
        self.agent.deleted_jobs.add('job')
        self.agent._handle_resource_response('worker', {'job_id': 'job'})
        self.agent._handle_create_resource_blocking('worker', {'job_id': 'job'})
        self.assertEqual(self.agent.job_responses, {})
        self.assertEqual(self.agent.job_capreg_allocated, {})


if __name__ == '__main__':
    unittest.main()
