import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from auto_refresh import AutoRefresh
from update_data import UpdateInProgress, SourceChanged


def wait_for(predicate, timeout=4):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('background job did not complete')


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base/'project'
        self.root.mkdir()
        self.services = []

    def tearDown(self):
        for service in self.services:
            service.close()
        self.temp.cleanup()

    def service(self, updater=lambda *args, **kwargs: None, **kwargs):
        service = AutoRefresh(self.root, updater=updater, interval=.02, debounce=.05, **kwargs)
        self.services.append(service)
        return service

    def test_upload_batch_coalesces_and_outputs_do_not_trigger_refresh(self):
        calls = []
        def updater(root, progress, snapshot):
            self.assertTrue(snapshot)
            progress('본문 추출 중')
            calls.append(sorted(p.name for p in (root/'Role01/dataset/files/uploads').iterdir()))
        service = self.service(updater)
        first = service.register_files([('course/a.txt', b'one')])
        second = service.register_files([('b.txt', b'two')])
        self.assertEqual(first['job_id'], second['job_id'])
        service.start()
        wait_for(lambda: service.job(first['job_id'])['status']=='ready')
        self.assertEqual(len(calls), 1)
        generated = self.root/'Role03/output'
        generated.mkdir(parents=True)
        (generated/'files.sqlite3').write_bytes(b'new DB')
        time.sleep(.15)
        self.assertEqual(len(calls), 1)
        (service.corpus/'uploads/b.txt').write_text('changed')
        wait_for(lambda: len(calls)==2)
        wait_for(lambda: service.status()['job']['status']=='ready')
        (service.corpus/'uploads/b.txt').unlink()
        wait_for(lambda: len(calls)==3)

    def test_changes_during_processing_run_next_without_overlap(self):
        entered, release = threading.Event(), threading.Event()
        calls, active = [], []
        def updater(root, **kwargs):
            self.assertFalse(active)
            active.append(True); calls.append(1)
            if len(calls)==1:
                entered.set(); self.assertTrue(release.wait(3))
            active.pop()
        service = self.service(updater)
        first = service.register_files([('a.txt', b'first')]); service.start()
        self.assertTrue(entered.wait(2))
        second = service.register_files([('a.txt', b'updated')])
        self.assertNotEqual(first['job_id'], second['job_id'])
        release.set()
        wait_for(lambda: service.job(second['job_id'])['status']=='ready')
        self.assertEqual(len(calls), 2)

    def test_source_folder_add_modify_delete_restart_and_unwatch(self):
        source = self.base/'notes'; source.mkdir()
        (source/'a.txt').write_text('first')
        service = self.service()
        folder = service.add_folder(str(source))
        service.poll_once()
        mirror = service.corpus/'watched'/folder['id']
        self.assertEqual((mirror/'a.txt').read_text(), 'first')
        (source/'a.txt').write_text('second')
        (source/'b.txt').write_text('new')
        service.poll_once()
        self.assertEqual((mirror/'a.txt').read_text(), 'second')
        (source/'a.txt').unlink()
        restarted = self.service()
        restarted.poll_once()
        self.assertFalse((mirror/'a.txt').exists())
        self.assertEqual((source/'b.txt').read_text(), 'new')
        restarted.remove_folder(folder['id'])
        (source/'b.txt').write_text('after stop')
        restarted.poll_once()
        self.assertEqual((mirror/'b.txt').read_text(), 'new')
        resumed=restarted.add_folder(str(source)); self.assertEqual(resumed['id'],folder['id'])
        restarted.poll_once(); self.assertEqual((mirror/'b.txt').read_text(),'after stop')

    def test_unavailable_folder_keeps_mirror_and_reports_error(self):
        source = self.base/'source'; source.mkdir()
        (source/'a.txt').write_text('keep')
        service = self.service(); folder=service.add_folder(str(source)); service.poll_once()
        source.rename(self.base/'disconnected')
        service.poll_once()
        self.assertEqual((service.corpus/'watched'/folder['id']/'a.txt').read_text(), 'keep')
        self.assertTrue(service.status()['folders'][0]['error'])

    def test_registration_validation_and_symlink_escape(self):
        service = self.service()
        for invalid in ['../bad.txt', '/tmp/bad.txt', 'C:\\bad.txt', '.git/config.txt', 'bad.exe']:
            with self.assertRaises(ValueError):
                service.register_files([('safe.txt', b'ok'), (invalid, b'bad')])
            self.assertFalse((service.corpus/'uploads/safe.txt').exists())
        with patch('auto_refresh.MAX_FILE_SIZE', 2), self.assertRaises(ValueError):
            service.register_files([('large.txt', b'123')])
        outside = self.base/'outside'; outside.mkdir()
        (service.corpus/'uploads').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): service.register_files([('escape.txt', b'bad')])
        with self.assertRaises(ValueError): service.add_folder(str(self.root))
        with self.assertRaises(ValueError): service.add_folder(str(self.base))

    def test_restart_detects_offline_changes_and_failed_job_is_visible(self):
        service = self.service(); job=service.register_files([('a.txt', b'old')]); service.start()
        wait_for(lambda: service.job(job['job_id'])['status']=='ready')
        service.close(); self.services.remove(service)
        (service.corpus/'uploads/a.txt').write_text('offline change')
        def fail(*args, **kwargs): raise RuntimeError('model unavailable')
        restarted=self.service(fail)
        self.assertIsNotNone(restarted.status()['job'])
        restarted.start()
        wait_for(lambda: restarted.status()['job']['status']=='failed')
        self.assertIn('model unavailable', restarted.status()['job']['error'])

    def test_external_update_lock_waits_and_preserves_job_tracking(self):
        calls=[]
        def updater(*args, **kwargs):
            calls.append(1)
            if len(calls)==1:
                service.register_files([('b.txt', b'second')])
                raise UpdateInProgress('busy')
        service=self.service(updater); first=service.register_files([('a.txt', b'first')]); service.start()
        wait_for(lambda: service.job(first['job_id'])['status']=='ready')
        self.assertEqual(len(calls), 2)

    def test_snapshot_change_is_retried_and_empty_text_is_reported(self):
        calls=[]
        def updater(root, **kwargs):
            calls.append(1)
            if len(calls)==1:
                raise SourceChanged('source changed during copy')
            (root/'Role01/extracted_text.csv').write_text('file_id,path,extraction_status\nF001,dataset/files/uploads/empty.txt,empty_text\n')
        service=self.service(updater); job=service.register_files([('empty.txt',b' ')])
        service.start();wait_for(lambda:service.job(job['job_id'])['status']=='ready')
        self.assertEqual(service.job(job['job_id'])['files'][0]['extraction_status'],'empty_text')
        self.assertEqual(len(calls),2)

    def test_hidden_files_generated_files_and_source_symlinks_are_ignored(self):
        source=self.base/'source'; source.mkdir()
        (source/'a.txt').write_text('visible')
        (source/'.hidden.txt').write_text('hidden')
        outside=self.base/'secret.txt'; outside.write_text('outside')
        (source/'linked.txt').symlink_to(outside)
        service=self.service(); folder=service.add_folder(str(source)); service.poll_once()
        mirror=service.corpus/'watched'/folder['id']
        self.assertEqual([p.name for p in mirror.iterdir()], ['a.txt'])


class RegistrationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.root=self.base/'project'; self.root.mkdir()
        self.controller=AutoRefresh(self.root, updater=lambda *args, **kwargs:None, interval=.02, debounce=.02).start()
        sys.path.insert(0, str(Path(__file__).resolve().parent/'Role04/scripts'))
        from serve_web import Handler
        class TestHandler(Handler):
            registration=self.controller
            service=None
            def log_message(self,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        self.thread=threading.Thread(target=self.server.serve_forever); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.controller.close(); self.temp.cleanup()

    def request(self, method, path, data=None, content_type='application/json', origin=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        headers={'Content-Type':content_type}
        if origin: headers['Origin']=origin
        conn.request(method,path,data,headers)
        response=conn.getresponse(); body=json.loads(response.read()); status=response.status
        conn.close(); return status,body

    def test_batch_upload_job_and_folder_contract(self):
        boundary='registration-boundary'
        data=(f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="a.txt"\r\n\r\nhello\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="paths"\r\n\r\n["course/a.txt"]\r\n--{boundary}--\r\n').encode()
        status,body=self.request('POST','/api/files/batch',data,f'multipart/form-data; boundary={boundary}')
        self.assertEqual(status,202)
        wait_for(lambda:self.request('GET','/api/jobs/'+body['job_id'])[1]['status']=='ready')
        self.assertEqual((self.controller.corpus/'uploads/course/a.txt').read_text(),'hello')
        source=self.base/'notes'; source.mkdir()
        status,body=self.request('POST','/api/folders',json.dumps({'path':str(source)}))
        self.assertEqual(status,201)
        self.assertEqual(self.request('DELETE','/api/folders/'+body['folder']['id'])[0],200)
        self.assertTrue(self.request('GET','/api/updates')[1]['watching'])
        self.assertTrue(self.request('GET','/api/health')[1]['capabilities']['upload'])

    def test_bad_payloads_and_cross_origin_are_rejected(self):
        self.assertEqual(self.request('POST','/api/files/batch','{}')[0],400)
        self.assertEqual(self.request('POST','/api/folders','[]')[0],400)
        self.assertEqual(self.request('POST','/api/folders','{}',origin='https://other.example')[0],403)
        self.assertEqual(self.request('DELETE','/api/folders/missing',origin='https://other.example')[0],403)
        self.assertEqual(self.request('GET','/api/jobs/missing')[0],404)


if __name__=='__main__': unittest.main()
