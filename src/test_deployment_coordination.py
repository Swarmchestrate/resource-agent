"""Exercise the deployment protocol without cloud or P2P dependencies."""
import ast
import asyncio
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch


def agent_class():
    tree = ast.parse(Path(__file__).with_name('ra_base.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ResourceAgent')
    names = {'_handle_master_info', '_handle_resource_created', '_maybe_request_sa_deployment',
             '_fail_deployment', '_deploy_sa_and_respond', '_handle_sa_deployed',
             '_create_worker_and_respond', '_clear_job_data', '_deploy_sa',
             '_notify_deployment_result', '_track_master_creation',
             '_handle_master_failed', '_handle_create_lead_resource_request',
             '_send_deployment_message'}
    cls.body = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name in names]
    scope = {'asyncio': asyncio, 'threading': threading, 'Path': Path,
             '__file__': str(Path(__file__).resolve().with_name('ra_base.py')),
             '_shutil': __import__('shutil')}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'ra_base.py', 'exec'), scope)
    return scope['ResourceAgent']


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.agent = a = agent_class()()
        a.deployment_lock = threading.RLock()
        a.resource_lock = threading.Lock()
        a.pending_deployments = {}
        a.sa_deployment_contexts = {}
        a.pending_deletions = {}
        a.deleted_jobs = set()
        a.logger = Mock()
        a.ra_id = 'hub'
        a.peer = Mock(peer_id='hub')
        a.config = {}
        a.job_clients = {'app': 'client'}
        a.job_states = {'app': {'state': 'Initialising'}}
        a.lead_resource = {'app': 'master'}
        a.job_offers = {'app': {
            'master': {'m': {'ids': {'ra_id': 'lead', 'ms_id': 'master'}}},
            'worker-1': {'w1': {'ids': {'ra_id': 'worker-ra', 'ms_id': 'worker'}}},
            'worker-2': {'w2': {'ids': {'ra_id': 'worker-ra', 'ms_id': 'worker'}}},
        }}
        self.timer_patch = patch.dict(a._handle_master_info.__globals__,
                                     threading=types.SimpleNamespace(Timer=Mock()))
        self.timer_patch.start()
        self.addCleanup(self.timer_patch.stop)
        self.master_message = {'job_id': 'app', 'master_info': {
            'cluster_name': 'app', 'master_ip': 'ip', 'k3s_token': 'token'}}

    def start(self, sender='lead'):
        asyncio.run(self.agent._handle_master_info(sender, self.master_message))

    def reply(self, node, sender='worker-ra', result='success'):
        self.agent._handle_resource_created(sender, {
            'job_id': 'app', 'node_name': node, 'result': result, 'message': 'creation error'})

    def requests(self):
        return [c for c in self.agent.peer.send.call_args_list if c.args[1] == 'MSG_DEPLOY_SA']

    def test_waits_for_each_node_and_sa_confirmation(self):
        self.start()
        self.assertEqual(len(self.agent.peer.send.call_args_list), 2)
        self.assertFalse(self.requests())
        self.reply('worker-1')
        self.reply('worker-1')  # Duplicate cannot count as a second worker.
        self.reply('worker-2', sender='wrong-ra')
        self.assertFalse(self.requests())
        self.reply('worker-2')
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(self.agent.job_states['app']['state'], 'Initialising')
        self.agent._handle_sa_deployed('wrong-ra', {'job_id': 'app', 'result': 'success'})
        self.assertEqual(self.agent.job_states['app']['state'], 'Initialising')
        self.agent._handle_sa_deployed('lead', {'job_id': 'app', 'result': 'success'})
        self.assertEqual(self.agent.job_states['app']['state'], 'Running')
        self.reply('worker-2')
        self.start()  # Repeated master-ready message cannot re-create workers.
        self.assertEqual(len(self.requests()), 1)

    def test_no_workers_requests_sa_immediately(self):
        self.agent.job_offers['app'] = {'master': self.agent.job_offers['app']['master']}
        self.start()
        self.assertEqual(len(self.requests()), 1)
        self.assertNotEqual(self.agent.job_states['app']['state'], 'Running')

    def test_worker_failure_blocks_sa_and_late_success(self):
        self.start()
        self.reply('worker-1', result='failure')
        self.reply('worker-1')
        self.reply('worker-2')
        self.assertFalse(self.requests())
        self.assertEqual(self.agent.job_states['app']['state'], 'Failed')

    def test_dispatch_failure_blocks_sa(self):
        self.agent.peer.send.side_effect = RuntimeError('offline')
        self.start()
        self.assertEqual(self.agent.job_states['app']['state'], 'Failed')
        self.assertFalse(self.requests())

    def test_responses_during_dispatch_are_not_lost(self):
        def send(target, kind, payload):
            if kind == 'MSG_CREATE_RESOURCE':
                self.reply(payload['instance']['node-name'])
        self.agent.peer.send.side_effect = send
        self.start()
        self.assertEqual(len(self.requests()), 1)

    def test_timeout_and_deletion_ignore_late_responses(self):
        self.start()
        timer_factory = self.agent._handle_master_info.__globals__['threading'].Timer
        timer_factory.call_args.args[1]()
        self.assertEqual(self.agent.job_states['app']['state'], 'Failed')
        self.assertEqual(self.final_responses()[0]['result'], 'failure')
        self.assertIn('Timed out', self.final_responses()[0]['message'])
        self.reply('worker-1')
        self.reply('worker-2')
        self.assertFalse(self.requests())

    def test_deleting_application_does_not_deploy(self):
        self.start()
        self.agent.pending_deletions['app'] = {}
        self.reply('worker-1')
        self.reply('worker-2')
        self.assertFalse(self.requests())

    def test_worker_sends_success_and_failure_after_creation(self):
        a = self.agent
        a.peer.peer_id = 'worker-ra'
        a._handle_create_resource_blocking = Mock()
        message = {'job_id': 'app', 'hub_ra': 'hub', 'instance': {'node-name': 'worker-1'}}
        a._create_worker_and_respond('lead', message)
        a._handle_create_resource_blocking.assert_called_once_with('lead', message)
        self.assertEqual(a.peer.send.call_args.args, ('hub', 'MSG_RESOURCE_CREATED', {
            'job_id': 'app', 'node_name': 'worker-1', 'result': 'success'}))
        a._handle_create_resource_blocking.side_effect = RuntimeError('cloud error')
        a._create_worker_and_respond('lead', message)
        self.assertEqual(a.peer.send.call_args.args[2]['result'], 'failure')
        self.assertEqual(a.peer.send.call_args.args[2]['message'], 'cloud error')

    def test_lead_deploys_once_and_replies_to_hub(self):
        a = self.agent
        a.peer.peer_id = 'lead'
        a.sa_deployment_contexts['app'] = {'hub_ra': 'hub', 'status': 'waiting'}
        a._deploy_sa = Mock()
        a._deploy_sa_and_respond('stranger', {'job_id': 'app'})
        a._deploy_sa.assert_not_called()
        a._deploy_sa_and_respond('hub', {'job_id': 'app'})
        a._deploy_sa_and_respond('hub', {'job_id': 'app'})
        a._deploy_sa.assert_called_once()
        self.assertEqual(a.peer.send.call_args.args, ('hub', 'MSG_SA_DEPLOYED', {
            'job_id': 'app', 'result': 'success'}))

    def test_sa_failure_reaches_hub(self):
        a = self.agent
        self.start()
        self.reply('worker-1')
        self.reply('worker-2')
        a.sa_deployment_contexts['app'] = {'hub_ra': 'hub', 'status': 'waiting'}
        a.peer.peer_id = 'lead'
        a._deploy_sa = Mock(side_effect=RuntimeError('SSH failed'))
        a._deploy_sa_and_respond('hub', {'job_id': 'app'})
        response = a.peer.send.call_args.args[2]
        self.assertEqual(response['result'], 'failure')
        a._handle_sa_deployed('lead', response)
        self.assertEqual(a.job_states['app']['state'], 'Failed')
        self.assertEqual(self.final_responses()[0]['result'], 'failure')
        self.assertEqual(self.final_responses()[0]['message'], 'SSH failed')

    def test_lead_creation_retains_context_without_deploying_sa(self):
        from test_sat_expansion import agent_class as creation_agent_class
        a = creation_agent_class()()
        a.ra_id = 'lead'
        a.logger = Mock()
        a.deleted_jobs = set()
        a.pending_deletions = {}
        a.job_capreg_allocated = {}
        a.deployment_lock = threading.RLock()
        a.sa_deployment_contexts = {}
        a.capacity_file = 'capacity.yaml'
        a.dry_run = False
        a.peer = Mock(peer_id='lead')
        a.capreg = Mock()
        a.capreg.resource_set_get_from_offer.return_value = None
        a._get_instance_node_labels = Mock(return_value={})
        a._deploy_sa = Mock()
        a._send_deployment_message = a.peer.send
        a._maybe_dump_capacity = Mock()
        sardou = Mock()
        sardou.return_value.get_cluster.return_value = {'node': {
            'ssh_key': '/key', 'ssh_user': 'ubuntu', 'edge_device_local_ip': 'private-ip'}}
        builder = Mock()
        builder.return_value.add_node.return_value = {
            'master_ip': 'public-ip', 'k3s_token': 'token', 'cluster_name': 'app'}
        offer = {'m': {'ids': {'ms_id': 'master', 'offer_id': 'm',
                              'res_type': 'edge', 'provider_id': 'edge'}}}
        message = {'job_id': 'app', 'hub_ra': 'hub', 'lead_resource': True,
                   'leader_resource_name': 'master', 'offer_info': {'master': offer},
                   'tosca': {'application': 'tosca'},
                   'instance': {'node-name': 'master', 'k3s_role': 'master', 'resource': offer}}
        scope = a._handle_create_lead_resource.__globals__
        with patch.dict(scope, Sardou=sardou, Swarmchestrate=builder,
                        _os=Mock(getenv=Mock(return_value='true'))):
            a._handle_create_lead_resource('hub', message)
        a._deploy_sa.assert_not_called()
        context = a.sa_deployment_contexts['app']
        self.assertEqual(context['master_ip'], 'public-ip')
        self.assertEqual(context['hub_ra'], 'hub')
        self.assertEqual(context['tosca'], message['tosca'])
        self.assertEqual(a.peer.send.call_args.args[1], 'MSG_MASTER_INFO')
        self.assertEqual(a.peer.send.call_args.args[2]['master_info']['master_ip'], 'private-ip')

    def test_cleanup_cancels_timer_and_discards_context(self):
        self.start()
        a = self.agent
        timer = a.pending_deployments['app']['timer']
        a.sa_deployment_contexts['app'] = {'ssh_key_path': '/key'}
        for name in ('job_responses', 'master_info', 'job_clients',
                     'job_capreg_allocated', 'job_tosca', 'tosca'):
            setattr(a, name, {})
        a._clear_job_data('app')
        timer.cancel.assert_called_once()
        self.assertNotIn('app', a.pending_deployments)
        self.assertNotIn('app', a.sa_deployment_contexts)
        self.reply('worker-1')
        self.assertFalse(self.requests())

    def test_local_deployment_delivery_preserves_sender_for_all_message_types(self):
        a = self.agent
        routes = {
            'MSG_CREATE_LEAD_RESOURCE': '_handle_create_lead_resource_request',
            'MSG_MASTER_INFO': '_handle_master_info_cb',
            'MSG_MASTER_FAILED': '_handle_master_failed',
            'MSG_CREATE_RESOURCE': '_handle_create_resource',
            'MSG_RESOURCE_CREATED': '_handle_resource_created',
            'MSG_DEPLOY_SA': '_handle_deploy_sa',
            'MSG_SA_DEPLOYED': '_handle_sa_deployed',
        }
        for name in routes.values():
            setattr(a, name, Mock())
        for kind, name in routes.items():
            with self.subTest(kind=kind):
                payload = {'job_id': 'app'}
                a._send_deployment_message('hub', kind, payload)
                getattr(a, name).assert_called_once_with('hub', payload)
        a.peer.send.assert_not_called()
        a._send_deployment_message('remote', 'MSG_MASTER_INFO', {'job_id': 'app'})
        a.peer.send.assert_called_once_with('remote', 'MSG_MASTER_INFO', {'job_id': 'app'})

    def test_hub_can_be_master_and_worker_through_final_client_notification(self):
        a = self.agent
        # Local delivery must work even if transport loopback strips the sender.
        a.job_offers['app']['master']['m']['ids']['ra_id'] = 'hub'
        for node in ('worker-1', 'worker-2'):
            next(iter(a.job_offers['app'][node].values()))['ids']['ra_id'] = 'hub'
        a.sa_deployment_contexts['app'] = {'hub_ra': 'hub', 'status': 'waiting'}
        a._deploy_sa = Mock()
        a._handle_create_lead_resource_request = Mock()
        a._handle_master_info_cb = lambda peer, message: asyncio.run(a._handle_master_info(peer, message))
        a._handle_create_resource = a._create_worker_and_respond
        a._handle_create_resource_blocking = Mock()
        a._handle_deploy_sa = a._deploy_sa_and_respond
        # A transport send to self would return a blank sender; no such send is allowed.
        def send(target, kind, payload):
            self.assertNotEqual(target, 'hub')
        a.peer.send.side_effect = send
        a._track_master_creation('app', 'hub')
        a._send_deployment_message('hub', 'MSG_MASTER_INFO', self.master_message)
        self.assertEqual(a._handle_create_resource_blocking.call_count, 2)
        a._deploy_sa.assert_called_once()
        self.assertEqual(a.job_states['app']['state'], 'Running')
        self.assertEqual(self.final_responses()[0]['result'], 'success')

    def final_responses(self):
        return [c.args[2] for c in self.agent.peer.send.call_args_list
                if c.args[0] == 'client' and c.args[1] == 'MSG_SUBMIT_RESPONSE']

    def test_final_success_only_after_sa_and_only_once(self):
        self.start()
        self.reply('worker-1')
        self.reply('worker-2')
        self.assertFalse(self.final_responses())
        message = {'job_id': 'app', 'result': 'success'}
        self.agent._handle_sa_deployed('lead', message)
        self.agent._handle_sa_deployed('lead', message)
        self.assertEqual(len(self.final_responses()), 1)
        self.assertEqual(self.final_responses()[0]['result'], 'success')
        self.assertTrue(self.final_responses()[0]['final'])

    def test_final_worker_failure_and_timeout(self):
        self.start()
        self.reply('worker-1', result='failure')
        self.reply('worker-2')
        self.assertEqual(len(self.final_responses()), 1)
        self.assertEqual(self.final_responses()[0]['result'], 'failure')
        self.assertIn('creation error', self.final_responses()[0]['message'])

    def test_master_failure_and_timeout_notify_client(self):
        for timeout in (False, True):
            with self.subTest(timeout=timeout):
                a = self.agent
                a.pending_deployments.clear()
                a.peer.reset_mock()
                a._track_master_creation('app', 'lead')
                if timeout:
                    factory = a._track_master_creation.__globals__['threading'].Timer
                    factory.call_args.args[1]()
                else:
                    a._handle_master_failed('lead', {'job_id': 'app', 'message': 'cloud error'})
                self.assertEqual(self.final_responses()[0]['result'], 'failure')
                self.assertEqual(a.job_states['app']['state'], 'Failed')

    def test_master_ready_transitions_from_master_tracking(self):
        self.agent._track_master_creation('app', 'lead')
        old_timer = self.agent.pending_deployments['app']['timer']
        self.start()
        old_timer.cancel.assert_called_once()
        self.assertEqual(self.agent.pending_deployments['app']['phase'], 'workers')
        self.assertFalse(self.final_responses())

    def test_prepares_files_and_uses_retained_public_ssh_address(self):
        a = self.agent
        a.hub_ra_ip = 'hub-ip'
        a.dry_run = False
        scope = a._deploy_sa.__globals__
        helpers = {name: Mock() for name in ('write_yaml', 'write_tosca_configmap',
                   'write_swarm_configmap', 'write_simdata_configmap', 'Swarmchestrate')}
        context = {'cluster_name': 'app', 'tosca': {}, 'lead_resource_name': 'master',
                   'offer_info': a.job_offers['app'], 'master_ip': 'public-ip',
                   'ssh_user': 'ubuntu', 'ssh_key_path': '/key', 'ssh_port': 22}
        with tempfile.TemporaryDirectory() as directory, patch.dict(scope, helpers):
            # Resolve generated relative paths in a temporary directory without chdir.
            root = Path(directory)
            (root / 'k3s').mkdir()
            (root / 'k3s/sa.yaml').write_text('kind: DaemonSet')
            def local_path(value):
                path = Path(value)
                return path if path.is_absolute() else root / path
            with patch.dict(scope, Path=local_path):
                a._deploy_sa('app', context)
                self.assertTrue((root / 'output/cluster_app/k3s-app/sa.yaml').exists())
                builder = helpers['Swarmchestrate'].return_value
                self.assertEqual(builder.deploy_manifests.call_args.kwargs['master_ip'], 'public-ip')
                self.assertEqual(helpers['write_swarm_configmap'].call_args.args[0], {
                    'LEADER': 'master', 'Worker': ['worker-1', 'worker-2']})
                a.dry_run = True
                builder.reset_mock()
                a._deploy_sa('app', context)
                builder.deploy_manifests.assert_not_called()


if __name__ == '__main__':
    unittest.main()
