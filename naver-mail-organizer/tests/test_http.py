"""Local HTTP checks only; no Naver, Cloudflare or actual mailbox writes."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import test_server
from test_server import s


class HttpOnly(unittest.TestCase):
    def setUp(self):
        self.fixture = test_server.Tests()
        self.fixture.setUp()
        self.http = s.ThreadingHTTPServer(('127.0.0.1', 0), s.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.http.server_address[1])

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.fixture.tearDown()

    def post(self, payload, token='unit-test-api-token', path='/mcp'):
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(), headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def call(self, name, arguments):
        response = self.post({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
        self.assertFalse(response['result']['isError'])
        return json.loads(response['result']['content'][0]['text'])

    def test_health_and_method_and_auth(self):
        with urllib.request.urlopen(self.base + '/healthz') as response:
            self.assertEqual(json.load(response), {'status': 'ok'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post({'method': 'tools/list'}, token='wrong')
        self.assertEqual(ctx.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + '/mcp')
        self.assertEqual(ctx.exception.code, 405)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post({'method': 'tools/list'}, path='/')
        self.assertEqual(ctx.exception.code, 404)

    def test_spam_tool_http_roundtrip(self):
        self.fixture.setup_spam()
        tools = self.post({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
        spam_tool = next(t for t in tools if t['name'] == 'naver_move_read_inbox_to_spam_batch')
        self.assertFalse(spam_tool['annotations']['readOnlyHint'])
        handles = [self.fixture.handle(1), self.fixture.handle(2)]
        self.assertTrue(self.call('naver_move_read_inbox_to_spam_batch', {'handles': handles})['dry_run'])
        self.assertEqual(self.call('naver_move_read_inbox_to_spam_batch', {'handles': handles, 'dry_run': False})['newly_verified_count'], 2)
        self.assertEqual(self.call('naver_verify_moves', {'handles': handles})['verified_count'], 2)

    def test_tool_discovery_and_batch_roundtrip(self):
        tools = self.post({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
        self.assertEqual(len(tools), 11)
        listed = self.call('naver_list_read_inbox', {'limit': 100})
        item = {'handle': listed['messages'][0]['handle'], 'destination': 'Work'}
        preview = self.call('naver_move_read_inbox_batch', {'items': [item]})
        self.assertEqual(preview['counts'], {'preview': 1})
        moved = self.call('naver_move_read_inbox_batch', {'items': [item], 'dry_run': False})
        self.assertEqual(moved['newly_verified_count'], 1)
        verified = self.call('naver_verify_moves', {'handles': [item['handle']]})
        self.assertEqual(verified['verified_count'], 1)
        history = self.call('naver_get_move_results', {})
        self.assertEqual(history['totals']['verified'], 1)
        self.assertEqual(len(self.fixture.commands('MOVE')), 1)

    def test_invalid_json_and_oversized_body(self):
        for payload in [b'{', b' ' * 262145]:
            req = urllib.request.Request(self.base + '/mcp', data=payload, headers={'Authorization': 'Bearer unit-test-api-token'})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 400)

