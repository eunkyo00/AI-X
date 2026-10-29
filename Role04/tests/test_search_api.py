"""HTTP contract regression checks; real-model verification is performed separately."""
import http.client
import json
import sys
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serve_web import Handler
from search_api import SearchService


class FakeService:
    catalog = {'F1': {'file_id': 'F1', 'name': 'sample.R'}}

    def search(self, query):
        return {'files': [self.catalog['F1']] if query else [], 'relations': []}


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class TestHandler(Handler):
            service = FakeService()

            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(TestHandler, directory=str(Path(__file__).resolve().parents[1] / 'web')))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        content = response.read()
        status = response.status
        conn.close()
        return status, content

    def test_health_files_and_search_contract(self):
        status, body = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['index_ready'])
        self.assertFalse(json.loads(body)['capabilities']['upload'])
        for method, path, body in [('GET', '/api/files', None), ('POST', '/api/search', '{"query":"SARIMA"}')]:
            status, response = self.request(method, path, body)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(response)['files'][0]['file_id'], 'F1')

    def test_invalid_input_and_unavailable_features(self):
        for body in ['{', '[]', '{"query":3}', json.dumps({'query': 'a' * 2001})]:
            self.assertEqual(self.request('POST', '/api/search', body)[0], 400)
        self.assertEqual(json.loads(self.request('POST', '/api/search', '{"query":" "}')[1])['files'], [])
        self.assertEqual(self.request('POST', '/api/search', '{"query":"x"}', 'https://other.example')[0], 403)
        self.assertEqual(self.request('POST', '/api/files', '{}')[0], 501)
        self.assertEqual(self.request('GET', '/api/files/F1/content')[0], 404)

    def test_bootstrap_and_metadata(self):
        self.assertIn(b'"base": "/api"', self.request('GET', '/runtime-config.js')[1])
        row = SearchService.file({'file_id': 'F1', 'filename': 'sample.R', 'path': 'dataset\\sample.R', 'modified_at': '2026.4.10 18:31', 'size_bytes': '123'})
        self.assertEqual(row['path'], 'dataset/sample.R')
        self.assertEqual(row['modified_at'], '2026-04-10T18:31:00')
        self.assertEqual(row['size'], 123)
        self.assertEqual(row['evidence'], [])
        self.assertNotIn('task_id', row)


if __name__ == '__main__':
    unittest.main()
