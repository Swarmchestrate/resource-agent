"""Client remains connected until a terminal submission response arrives."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


def client_class():
    tree = ast.parse(Path(__file__).with_name('job_submission_client.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                and n.name == '_handle_submit_response']
    scope = {'Any': object}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'client.py', 'exec'), scope)
    return scope['SwarmchestrateClient']


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.client = client_class()()
        self.client.logger = Mock()
        self.client.stop_client = Mock()
        self.client.job_complete = False
        self.print_patch = patch('builtins.print')
        self.print_patch.start()
        self.addCleanup(self.print_patch.stop)

    def test_acceptance_waits_for_final_success(self):
        c = self.client
        c._handle_submit_response('hub', {'job_id': 'app', 'result': 'accepted', 'final': False})
        c.stop_client.assert_not_called()
        self.assertFalse(c.job_complete)
        self.assertEqual(c.swarm_id, 'app')
        c._handle_submit_response('hub', {'job_id': 'app', 'result': 'success', 'final': True})
        self.assertTrue(c.job_complete)
        c.stop_client.assert_called_once()
        self.assertEqual(c.submission_result['result'], 'success')
        c._handle_submit_response('hub', {'job_id': 'app', 'result': 'success', 'final': True})
        c.stop_client.assert_called_once()

    def test_failure_with_or_without_acceptance_stops_client(self):
        self.client._handle_submit_response('hub', {'result': 'failure', 'message': 'Invalid SAT'})
        self.client.stop_client.assert_called_once()
        self.assertTrue(self.client.job_complete)
        self.assertEqual(self.client.submission_result['message'], 'Invalid SAT')

    def test_nonfinal_success_does_not_stop_client(self):
        self.client._handle_submit_response('hub', {'job_id': 'app', 'result': 'success', 'final': False})
        self.client.stop_client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
