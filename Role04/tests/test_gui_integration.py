"""Meaningful adapter regressions without downloading an embedding model."""
import csv
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from search_api import SearchService, BusyError


class AdapterTests(unittest.TestCase):
    def service(self, root):
        root = root.resolve()
        one = root / 'Role01'
        original = one / 'dataset' / 'files'
        original.mkdir(parents=True)
        (original / 'one.txt').write_text('first')
        (original / 'two.txt').write_text('related')
        rows = [{'file_id': f'F{i:03d}', 'filename': name, 'path': 'dataset/files/' + name,
                 'modified_at': '2026-04-10 12:30:00', 'created_at': '2026-03-01 09:00:00', 'size_bytes': '5'}
                for i, name in enumerate(('one.txt', 'two.txt'), 1)]
        with (one / 'metadata.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0])
            writer.writeheader(); writer.writerows(rows)
        class IDs(list):
            def astype(self, kind): return self
        class Engine:
            df = {'file_id': IDs(['F001', 'F002'])}
            def refresh(self): pass
            def search_files(self, query, top_k):
                return [{'file_id': 'F001', 'score': .8, 'chunk_text': 'first'}]
            def get_related_files(self, file_id, top_n):
                return [{'target_file_id': 'F002', 'relation_type': 'references', 'evidence': 'two.txt'}]
        service = SearchService.__new__(SearchService)
        service.backend = root
        service.engine_dir = one
        service.original_root = original.resolve()
        service.engine = Engine()
        service.lock = threading.RLock()
        service.job_lock = threading.Lock()
        service.jobs = {}
        service.active_job = None
        service._reload_catalog()
        return service

    def test_search_keeps_originals_and_supplies_related_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            for _ in range(2):
                result = service.search('first')
                self.assertTrue(result['files'][0]['content_available'])
                self.assertEqual(service.content('F001').read_text(), 'first')
                self.assertEqual(result['catalog'][0]['file_id'], 'F002')
                self.assertEqual(result['relations'][0]['certainty'], 'inferred')
                self.assertEqual(result['relations'][0]['evidence'], 'two.txt')

    def test_resolved_db_reference_replaces_heuristic_for_same_pair(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            service=self.service(Path(directory))
            folder=service.backend/'Role03'/'output';folder.mkdir(parents=True)
            with sqlite3.connect(folder/'files.sqlite3') as db:
                db.execute('CREATE TABLE relations(source_id, target_id, status, relation_type, evidence)')
                db.execute('INSERT INTO relations VALUES(?,?,?,?,?)',('F001','F002','resolved','reads','read_csv("two.txt")'))
            db.close()
            links=service.search('first')['relations']
            self.assertEqual(len(links),1)
            self.assertEqual(links[0]['certainty'],'confirmed')
            self.assertIn('참조',links[0]['label'])
            self.assertEqual(links[0]['evidence'],'read_csv("two.txt")')

    def test_busy_search_and_upload_reject_instead_of_mutating_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            service.active_job = 'busy'
            with self.assertRaises(BusyError): service.search('x')
            with self.assertRaises(BusyError): service.add('new.txt', b'new')
            self.assertFalse((service.original_root / 'uploads').exists())

    def test_upload_validation_precedes_writes_and_ids_are_reserved(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            for name, relative, modified in [('new.txt', '../new.txt', None), ('new.png', '', None),
                                             ('new.txt', '', 'nan'), ('new.txt', '', 'invalid')]:
                with self.assertRaises(ValueError):
                    service.add(name, b'body', relative, modified)
            self.assertFalse((service.original_root / 'uploads').exists())
            captured = []
            service.start_refresh = lambda upload=None: captured.append(upload) or 'job1'
            result = service.add('한글 메모.txt', b'body', 'folder/한글 메모.txt')
            self.assertEqual(result['file']['file_id'], 'F003')
            self.assertEqual(captured[0]['file_id'], 'F003')
            path = service.engine_dir / captured[0]['path']
            self.assertEqual(path.read_bytes(), b'body')

    def test_job_reports_copy_and_unknown_job(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(Path(directory))
            service.jobs['one'] = {'status': 'failed', 'error': 'parser error'}
            result = service.job('one'); result['status'] = 'ready'
            self.assertEqual(service.job('one')['status'], 'failed')
            with self.assertRaises(FileNotFoundError): service.job('unknown')



class VerifiedCacheTests(unittest.TestCase):
    def test_prior_text_reuse_requires_exact_original_hash(self):
        import hashlib
        import json
        from refresh_workspace import seed_verified_texts
        with tempfile.TemporaryDirectory() as directory:
            one=Path(directory)
            files=one/'dataset'/'files'; files.mkdir(parents=True)
            original=files/'memo.txt'; original.write_bytes(b'unchanged')
            row={'file_id':'F001','filename':'memo.txt','path':'dataset/files/memo.txt',
                 'extracted_text':'verified previous content','extraction_status':'success'}
            for name in ('metadata.csv','.previous_extracted_text.csv'):
                with (one/name).open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=row);writer.writeheader();writer.writerow(row)
            source=one/'prior-cache.json'
            source.write_text(json.dumps({'F001':{'path':row['path'],'sha256':hashlib.sha256(b'unchanged').hexdigest()}}))
            seed_verified_texts(one,source)
            self.assertIn('F001',json.loads((one/'.extraction_cache.json').read_text()))
            original.write_bytes(b'changed')
            seed_verified_texts(one,source)
            self.assertEqual(json.loads((one/'.extraction_cache.json').read_text()),{})


class FailureRecoveryTests(unittest.TestCase):
    service = AdapterTests.service
    def test_failed_upload_is_quarantined_and_previous_catalog_stays_available(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            service=self.service(Path(directory))
            for name in ('extracted_text.csv','file_relations.csv','.extraction_cache.json'):
                (service.engine_dir/name).write_text('{}')
            (service.backend/'Role03').mkdir()
            (service.backend/'Role02').mkdir()
            (service.backend/'update_data.py').write_text('# fixture')
            service.start_refresh=lambda upload=None: 'job1'
            result=service.add('invalid.txt',b'new content')
            file_id=result['file']['file_id']
            path=next(service.original_root.rglob('invalid.txt'))
            row={'file_id':file_id,'filename':'invalid.txt','path':path.relative_to(service.engine_dir).as_posix()}
            service.jobs['job1']={'status':'processing'};service.active_job='job1'
            with patch('search_api.subprocess.run',side_effect=RuntimeError('parser failed')):
                service._run_refresh('job1',row)
            self.assertEqual(service.job('job1')['status'],'failed')
            self.assertIsNone(service.active_job)
            self.assertFalse(path.exists())
            self.assertEqual((service.backend/'failed_uploads'/'job1'/'invalid.txt').read_bytes(),b'new content')
            self.assertEqual(service.content('F001').read_text(),'first')


if __name__ == '__main__': unittest.main()
