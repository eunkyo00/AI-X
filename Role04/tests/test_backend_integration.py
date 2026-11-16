"""Focused wiring checks without downloading models or modifying real data."""
import csv
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'Role04/scripts'))
from search_api import SearchService
from Role01.automation_code.file_watcher import create_watcher
from update_data import update


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


class IntegrationTests(unittest.TestCase):
    def test_csv_join_and_search_use_file_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one, two = root/'Role01', root/'Role02'
            write_csv(one/'metadata.csv', [dict(file_id='F2', filename='same.txt', role='', project='manual'),
                                            dict(file_id='F1', filename='same.txt', role='manual', project='')])
            write_csv(one/'extracted_text.csv', [dict(file_id='F1', extraction_status='success'),
                                                 dict(file_id='F2', extraction_status='success')])
            write_csv(two/'metadata_description_generated.csv', [dict(file_id='F1', description='first'),
                                                                  dict(file_id='F2', description='second')])
            write_csv(two/'metadata_classification_generated.csv', [
                dict(file_id='F2', predicted_role='code', role_needs_confirmation='False',
                     predicted_project='ignored', project_needs_confirmation='False', year_month='2026-11'),
                dict(file_id='F1', predicted_role='ignored', role_needs_confirmation='False',
                     predicted_project='uncertain', project_needs_confirmation='True', year_month='2026-10')])
            class Engine:
                def search_files(self, query, top_k):
                    return [dict(file_id='F2', score=.8, chunk_text='body')]
            service = SearchService.__new__(SearchService)
            service.engine_dir, service.lock, service.engine = one, threading.Lock(), Engine()
            result = service.search('query')['files'][0]
            self.assertEqual((result['file_id'], result['summary'], result['role']), ('F2', 'second', 'code'))
            self.assertEqual((result['project'], result['year_month']), ('manual', '2026-11'))
            self.assertEqual(service.catalog['F1']['role'], 'manual')
            self.assertEqual(service.catalog['F1']['project'], '')
            write_csv(two/'metadata_description_generated.csv', [dict(file_id='F2', description='changed')])
            self.assertEqual(service.search('query')['files'][0]['summary'], 'changed')

    def test_watcher_queues_integrated_pipeline_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            done = threading.Event()
            calls = []
            def updater(root, **kwargs):
                calls.append(kwargs)
                done.set()
            with patch('update_data.update', updater):
                watcher = create_watcher(Path(directory))
            watcher.debounce = .01
            watcher.request()
            watcher.start()
            try:
                self.assertTrue(done.wait(3))
            finally:
                watcher.close()
            self.assertTrue(calls[0]['integrated'])
            self.assertTrue(calls[0]['snapshot'])
            self.assertTrue(all(not thread.is_alive() for thread in watcher.threads))

    def test_pipeline_failure_keeps_live_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('Role01/paths.py', 'Role01/file_reload_code.py', 'Role01/extract_content.py',
                         'Role01/refresh_search.py', 'Role01/file_reload_append_only.py',
                         'Role03/file_db.py', 'update_pipeline_integrated.py',
                         'Role02/description_generator.py', 'Role02/classify_metadata.py',
                         'Role02/project_classifier.py', 'Role02/project_classifier_v3.py', 'Role02/role_classifier.py'):
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('# fixture')
            (root/'Role01/dataset/files').mkdir(parents=True)
            live = root/'Role01/metadata.csv'
            live.write_text('file_id,filename\nF1,original.txt\n')
            calls = []
            def runner(script, *args):
                calls.append(script.name)
                self.assertEqual(script.name, 'update_pipeline_integrated.py')
                self.assertTrue((script.parent/'Role02/classify_metadata.py').is_file())
                raise RuntimeError('Qwen unavailable')
            with self.assertRaisesRegex(RuntimeError, 'Qwen unavailable'):
                update(root, runner=runner, integrated=True, snapshot=True)
            self.assertEqual(calls, ['update_pipeline_integrated.py'])
            self.assertIn('original.txt', live.read_text())
            self.assertFalse((root/'.update-data.lock').exists())

    def test_integrated_pipeline_publishes_csvs_together(self):
        from update_data import ARTIFACTS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ('Role01/paths.py', 'Role01/file_reload_code.py', 'Role01/extract_content.py',
                             'Role01/refresh_search.py', 'Role01/file_reload_append_only.py',
                             'Role03/file_db.py', 'update_pipeline_integrated.py',
                             'Role02/description_generator.py', 'Role02/classify_metadata.py',
                             'Role02/project_classifier.py', 'Role02/project_classifier_v3.py', 'Role02/role_classifier.py'):
                path = root/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# fixture')
            (root/'Role01/dataset/files').mkdir(parents=True)
            calls = []
            def runner(script, *args):
                calls.append(script.name)
                if script.name == 'update_pipeline_integrated.py':
                    stage = script.parent
                    write_csv(stage/'Role01/metadata.csv', [dict(file_id='F1', filename='new.txt')])
                    write_csv(stage/'Role01/extracted_text.csv', [dict(file_id='F1', extraction_status='success')])
                    for name, row in (
                        ('metadata_description_generated.csv', dict(file_id='F1', description='Qwen result')),
                        ('metadata_classification_generated.csv', dict(file_id='F1', predicted_role='code'))):
                        write_csv(stage/'Role02'/name, [row])
                    (stage/'Role02/description_hashes.json').write_text('{}')
                    (stage/'Role01/.extraction_cache.json').write_text('{}')
                    (stage/'Role01/search_index').mkdir()
                    (stage/'Role01/search_index/index.json').write_text('{}')
                else:
                    self.assertEqual(script.name, 'file_db.py')
                    for relative in ARTIFACTS:
                        if relative.startswith('Role03/'):
                            path = script.parent.parent/relative
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text('db result')
            update(root, runner=runner, integrated=True)
            self.assertEqual(calls, ['update_pipeline_integrated.py', 'file_db.py'])
            self.assertIn('Qwen result', (root/'Role02/metadata_description_generated.csv').read_text())
            self.assertIn('code', (root/'Role02/metadata_classification_generated.csv').read_text())
            self.assertIn('F1', (root/'Role01/metadata.csv').read_text())
            self.assertFalse((root/'.update-data.lock').exists())


if __name__ == '__main__':
    unittest.main()
