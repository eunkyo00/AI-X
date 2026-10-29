"""HTTP contract regression checks; real-model verification is performed separately."""
import http.client
import json
import sys
import threading
import unittest
import tempfile
import base64
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serve_web import Handler
from search_api import SearchService, original_path


class FakeService:
    catalog = {'F1': {'file_id': 'F1', 'name': 'sample.R'}}

    def content(self, file_id):
        raise FileNotFoundError('missing')

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

    def test_catalog_refreshes_after_engine_reload(self):
        class Frame:
            def to_dict(self, orient):
                return [{'file_id': 'NEW', 'filename': 'new.txt'}]
        class Engine:
            df = Frame()
            def search_files(self, query, top_k):
                return [{'file_id': 'NEW', 'score': 1.0, 'chunk_text': 'new content'}]
        service = SearchService.__new__(SearchService)
        service.lock = threading.Lock()
        service.engine = Engine()
        service.catalog = {'OLD': {'file_id': 'OLD'}}
        result = service.search('new')
        self.assertEqual(result['files'][0]['file_id'], 'NEW')
        self.assertEqual(set(service.catalog), {'NEW'})

    def test_bootstrap_and_metadata(self):
        self.assertIn(b'"base": "/api"', self.request('GET', '/runtime-config.js')[1])
        row = SearchService.file({'file_id': 'F1', 'filename': 'sample.R', 'path': 'dataset\\sample.R', 'modified_at': '2026.4.10 18:31', 'size_bytes': '123'})
        self.assertEqual(row['path'], 'dataset/sample.R')
        self.assertEqual(row['modified_at'], '2026-04-10T18:31:00')
        self.assertEqual(row['size'], 123)
        self.assertEqual(row['evidence'], [])
        self.assertNotIn('task_id', row)


    def test_original_path_and_binary_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = original_path(root, 'F1', '한글 파일.PDF')
            path.parent.mkdir()
            content = b'%PDF-1.4\noriginal-bytes\x00'
            path.write_bytes(content)
            service = SearchService.__new__(SearchService)
            service.original_root = path.parent.resolve()
            service.originals = {'F1': path}
            service.catalog = FakeService.catalog
            handler = self.server.RequestHandlerClass.func
            previous = handler.service
            handler.service = service
            try:
                status, body = self.request('GET', '/api/files/F1/content')
                self.assertEqual(status, 200)
                self.assertEqual(body, content)
                self.assertEqual(self.request('GET', '/api/files/unknown/content')[0], 404)
                self.assertEqual(self.request('GET', '/api/files/%2e%2e%2fsecret/content')[0], 404)
                path.unlink()
                self.assertEqual(self.request('GET', '/api/files/F1/content')[0], 404)
            finally:
                handler.service = previous
            with self.assertRaises(ValueError):
                original_path(root, '../escape', 'x.pdf')
            outside = root / 'outside.pdf'
            outside.write_bytes(b'private')
            path.symlink_to(outside)
            with self.assertRaises(FileNotFoundError):
                service.content('F1')


    def test_pdf_pages_and_invalid_page(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'F1.pdf'
            with pymupdf.open() as doc:
                doc.new_page().insert_text((50, 50), 'Original page one')
                doc.new_page().insert_text((50, 50), 'Original page two')
                doc.save(path)
            service = SearchService.__new__(SearchService)
            service.original_root = Path(folder).resolve()
            service.originals = {'F1': path}
            service.catalog = FakeService.catalog
            handler = self.server.RequestHandlerClass.func
            previous = handler.service
            handler.service = service
            try:
                status, body = self.request('GET', '/api/files/F1/preview?page=2')
                self.assertEqual(status, 200)
                result = json.loads(body)
                self.assertEqual((result['page'],result['page_count']), (2,2))
                self.assertTrue(base64.b64decode(result['image_base64']).startswith(b'\x89PNG\r\n\x1a\n'))
                for page in ['0','3','bad']:
                    self.assertEqual(self.request('GET', '/api/files/F1/preview?page='+page)[0],400)
            finally:
                handler.service = previous


if __name__ == '__main__':
    unittest.main()
