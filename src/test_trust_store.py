"""Trust records use the provider CAP ID as their OptimusDB _id."""

import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


def trust_store_class():
    # Exercise the real class without importing OptimusDB's optional HTTP client.
    tree = ast.parse(Path(__file__).with_name('trust_store.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'TrustStore')
    scope = {'OptimusDBClient': Mock, 'TRUST_STORE': 'kbtrust'}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'trust_store.py', 'exec'), scope)
    return scope['TrustStore']


class TrustStoreTests(unittest.TestCase):
    def test_lookup_by_cap_id(self):
        client = Mock()
        client.get.return_value = {'data': [{'_id': 'cap-a',
                                             'trust_level': 0.82}]}
        self.assertEqual(trust_store_class()(client).get_trust_score('cap-a', default=1.0), 0.82)
        client.get.assert_called_once_with(
            criteria=[{'_id': 'cap-a'}], dstype='kbtrust')

    def test_missing_cap_or_record_uses_default(self):
        client = Mock()
        store = trust_store_class()(client)
        self.assertEqual(store.get_trust_score(None, default=1.0), 1.0)
        client.get.assert_not_called()
        client.get.return_value = {'data': []}
        self.assertEqual(store.get_trust_score('cap-a', default=1.0), 1.0)
        client.get.return_value = {'data': [{'_id': 'cap-a'}]}
        self.assertEqual(store.get_trust_score('cap-a', default=1.0), 1.0)


if __name__ == '__main__':
    unittest.main()
