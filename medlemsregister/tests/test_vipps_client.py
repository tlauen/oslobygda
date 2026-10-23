import unittest
from unittest.mock import patch
from vipps_client import VippsClient, amount_ore


class VippsClientTests(unittest.TestCase):
    def test_amounts_without_float_rounding(self):
        self.assertEqual(amount_ore('100'),10000)
        self.assertEqual(amount_ore('5,50'),550)
        for value in ('0','-1','1.001','nan','1e3','1000001',100):
            with self.assertRaises(ValueError):
                amount_ore(value)

    def test_test_environment_and_idempotency(self):
        client=VippsClient('test-id','test-secret','test-key','123456')
        self.assertEqual(client.base,'https://apitest.vipps.no')
        with patch.object(client,'_request',side_effect=[{'access_token':'test-token','expires_in':3600},{},{}]) as request:
            client.create('bygdelista-123456',10000,'https://bygdelista.oslobygda.no/betaling','saved-create-key')
            client.capture('bygdelista-123456',10000,'saved-capture-key')
            create=request.call_args_list[1]
            self.assertEqual(create.args[2]['Idempotency-Key'],'saved-create-key')
            self.assertEqual(create.args[3]['amount']['value'],10000)
            self.assertNotIn('client_secret',create.args[2])
            capture=request.call_args_list[2]
            self.assertEqual(capture.args[3]['modificationAmount']['value'],10000)
            self.assertEqual(capture.args[2]['Idempotency-Key'],'saved-capture-key')

    def test_no_api_calls_for_invalid_requests(self):
        client=VippsClient('test-id','test-secret','test-key','123456')
        with patch.object(client,'_request') as request:
            with self.assertRaises(ValueError):
                client.create('invalid/path',10000,'https://example.org','key')
            with self.assertRaises(ValueError):
                client.create('bygdelista-123456',10000,'http://example.org','key')
            with self.assertRaises(ValueError):
                client.capture('bygdelista-123456',True,'key')
            request.assert_not_called()
