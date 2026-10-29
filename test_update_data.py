import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from update_data import ARTIFACTS, ROOT, publish, update


class UpdateTests(unittest.TestCase):
    def test_portable_paths_and_preserved_ids_and_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('paths.py', 'file_reload_code.py'):
                shutil.copy2(ROOT/'Role01'/name, root/name)
            folder = root/'dataset/files/sample'
            folder.mkdir(parents=True)
            (folder/'old.txt').write_text('changed')
            (folder/'new.txt').write_text('new')
            (folder/'.DS_Store').write_text('system')
            (folder/'.Rhistory').write_text('history')
            original = dict(file_id='F161', filename='old.txt', path=r'C:\old\dataset\files\sample\old.txt',
                            project='project', role='notes', description='keep me')
            with (root/'metadata.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=original)
                writer.writeheader(); writer.writerow(original)
            for _ in range(2):
                subprocess.run([sys.executable, str(root/'file_reload_code.py')], cwd='/', check=True, capture_output=True)
                with (root/'metadata.csv').open(encoding='utf-8-sig', newline='') as stream:
                    rows = {r['filename']:r for r in csv.DictReader(stream)}
                self.assertEqual(rows['old.txt']['file_id'], 'F161')
                self.assertEqual(rows['old.txt']['description'], 'keep me')
                self.assertEqual(rows['old.txt']['project'], 'project')
                self.assertEqual(rows['new.txt']['file_id'], 'F162')
                self.assertEqual(set(rows), {'new.txt', 'old.txt'})
                self.assertEqual(rows['old.txt']['path'], 'dataset/files/sample/old.txt')

    def test_extraction_uses_portable_paths_outside_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('paths.py', 'extract_content.py'):
                shutil.copy2(ROOT/'Role01'/name, root/name)
            folder = root/'dataset/files'
            folder.mkdir(parents=True)
            (folder/'sample.txt').write_text('본문 내용', encoding='utf-8')
            row = dict(file_id='F001', path=r'dataset\files\sample.txt')
            with (root/'metadata.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=row)
                writer.writeheader(); writer.writerow(row)
            subprocess.run([sys.executable, str(root/'extract_content.py')], cwd='/', check=True, capture_output=True)
            with (root/'extracted_text.csv').open(encoding='utf-8-sig', newline='') as stream:
                result = next(csv.DictReader(stream))
            self.assertEqual(result['extraction_status'], 'success')
            self.assertEqual(result['extracted_text'], '본문 내용')
            self.assertEqual(result['path'], 'dataset/files/sample.txt')

    def test_existing_ocr_reused_only_for_matching_source_hash(self):
        import hashlib
        import pymupdf
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('paths.py', 'extract_content.py'):
                shutil.copy2(ROOT/'Role01'/name, root/name)
            # Force the no-OCR environment without depending on host installations.
            folder = root/'dataset/files'
            folder.mkdir(parents=True)
            original = folder/'scan.pdf'
            document = pymupdf.open()
            document.new_page(); document.save(original); document.close()
            row = dict(file_id='F001', path='dataset/files/scan.pdf', filename='scan.pdf',
                       extraction_status='success', extracted_text='verified old OCR')
            audit = dict(file_id='F001', source_sha256=hashlib.sha256(original.read_bytes()).hexdigest())
            for name, record in (('metadata.csv', row), ('.previous_extracted_text.csv', row), ('.previous_audit.csv', audit)):
                with (root/name).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=record)
                    writer.writeheader(); writer.writerow(record)
            import os
            env = dict(os.environ, TESSERACT_CMD='')
            for unchanged in (True, False):
                if not unchanged:
                    with original.open('ab') as stream:
                        stream.write(b'\n% source changed\n')
                subprocess.run([sys.executable, '-c', 'import sys,runpy; sys.modules["pytesseract"]=None; sys.path.insert(0,sys.argv[1]); runpy.run_path(sys.argv[1]+"/extract_content.py",run_name="__main__")', str(root)], check=True, capture_output=True, env=env)
                with (root/'extracted_text.csv').open(encoding='utf-8-sig', newline='') as stream:
                    result = next(csv.DictReader(stream))
                if unchanged:
                    self.assertEqual(result['extracted_text'], 'verified old OCR')
                else:
                    self.assertTrue(result['extraction_status'].startswith('error: OCRUnavailable'))

    def test_failed_stage_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for role in ('Role01', 'Role03'):
                (root/role).mkdir()
            (root/'Role01/dataset').mkdir()
            for name in ('paths.py', 'file_reload_code.py', 'extract_content.py', 'refresh_search.py'):
                shutil.copy2(ROOT/'Role01'/name, root/'Role01'/name)
            shutil.copy2(ROOT/'Role03/file_db.py', root/'Role03/file_db.py')
            original = b'original metadata'
            (root/'Role01/metadata.csv').write_bytes(original)
            calls = []
            def failing_runner(script, *args):
                calls.append(script.name)
                if script.name == 'extract_content.py':
                    (script.parent/'extracted_text.csv').write_text('filename,extraction_status\nsample.txt,success\n')
                if script.name == 'refresh_search.py':
                    raise RuntimeError('injected search failure')
            with self.assertRaisesRegex(RuntimeError, 'injected search failure'):
                update(root, runner=failing_runner)
            self.assertEqual(len(calls), 4)
            self.assertEqual((root/'Role01/metadata.csv').read_bytes(), original)
            self.assertFalse((root/'.update-data.lock').exists())

    def test_publish_rolls_back_all_previous_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root, stage = Path(directory)/'live', Path(directory)/'stage'
            root.mkdir(); stage.mkdir()
            for relative in ARTIFACTS:
                live, new = root/relative, stage/relative
                live.parent.mkdir(parents=True, exist_ok=True)
                new.parent.mkdir(parents=True, exist_ok=True)
                live.write_text('old'); new.write_text('new')
            # Late failure after other artifacts have been replaced.
            (stage/ARTIFACTS[-1]).unlink()
            with self.assertRaises(FileNotFoundError):
                publish(root, stage)
            for relative in ARTIFACTS:
                self.assertEqual((root/relative).read_text(), 'old')

    def test_full_update_and_empty_corpus(self):
        import numpy as np
        sys.path.insert(0, str(ROOT/'Role01'))
        from refresh_search import build_index
        from update_data import run_step
        class Encoder:
            def encode(self, documents, **kwargs):
                return np.ones((len(documents), 3))
        def runner(script, *args):
            if script.name == 'refresh_search.py':
                build_index(script.parent/'extracted_text.csv', script.parent/'metadata.csv',
                            script.parent/'search_index', encoder=Encoder())
            else:
                run_step(script, *args)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for role in ('Role01', 'Role03'):
                (root/role).mkdir()
            for name in ('paths.py', 'file_reload_code.py', 'extract_content.py', 'refresh_search.py'):
                shutil.copy2(ROOT/'Role01'/name, root/'Role01'/name)
            shutil.copy2(ROOT/'Role03/file_db.py', root/'Role03/file_db.py')
            folder = root/'Role01/dataset/files'
            folder.mkdir(parents=True)
            sample = folder/'sample.txt'
            sample.write_text('sample text')
            update(root, runner=runner)
            import sqlite3
            with sqlite3.connect(root/'Role03/output/files.sqlite3') as db:
                row = db.execute('SELECT file_id, extracted_text, local_path FROM files').fetchone()
            self.assertEqual(row[:2], ('F001', 'sample text'))
            self.assertEqual(Path(row[2]).resolve(), sample.resolve())
            sample.unlink()
            update(root, runner=runner)
            with sqlite3.connect(root/'Role03/output/files.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM files').fetchone()[0], 0)
            self.assertTrue((root/'Role03/output/relations.csv').is_file())

    def test_search_reloads_published_index(self):
        import numpy as np
        sys.path.insert(0, str(ROOT/'Role01'))
        import refresh_search as search_model
        class Encoder:
            def encode(self, documents, **kwargs):
                return np.ones((len(documents), 3))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(search_model, 'BASE_DIR', root), patch.object(search_model, 'load_model', return_value=Encoder()):
                engine = search_model.SearchEngine()
                for content in ('first content', 'updated content'):
                    row = dict(file_id='F001', filename='sample.txt', extracted_text=content, path='dataset/files/sample.txt')
                    for name in ('extracted_text.csv', 'metadata.csv'):
                        with (root/name).open('w', newline='') as stream:
                            writer = csv.DictWriter(stream, fieldnames=row)
                            writer.writeheader(); writer.writerow(row)
                    search_model.build_index(root/'extracted_text.csv', root/'metadata.csv', root/'search_index', encoder=Encoder())
                    self.assertEqual(engine.search('sample')[0]['chunk_text'], content)

    def test_gui_engine_uses_shared_index_and_reloads(self):
        import numpy as np
        sys.path.insert(0, str(ROOT/'Role01'))
        from types import SimpleNamespace
        with patch.dict(sys.modules, {"sentence_transformers": SimpleNamespace(SentenceTransformer=lambda *args: None)}):
            import search_engine
        from refresh_search import build_index
        class Encoder:
            def encode(self, documents, **kwargs):
                return np.ones((len(documents), 3))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(search_engine, 'BASE_DIR', root), patch.object(search_engine, 'SentenceTransformer', return_value=Encoder()):
                engine = None
                for file_id in ('F001', 'F002'):
                    row = dict(file_id=file_id, filename='sample.txt', extracted_text='sample', description='notes', path='dataset/files/sample.txt')
                    for name in ('extracted_text.csv', 'metadata.csv'):
                        with (root/name).open('w', newline='') as stream:
                            writer = csv.DictWriter(stream, fieldnames=row)
                            writer.writeheader(); writer.writerow(row)
                    build_index(root/'extracted_text.csv', root/'metadata.csv', root/'search_index', encoder=Encoder())
                    if engine is None:
                        engine = search_engine.SearchEngine(root/'extracted_text.csv', root/'metadata.csv')
                    self.assertEqual(engine.search_files('sample')[0]['file_id'], file_id)
                    self.assertEqual(engine.df['file_id'].tolist(), [file_id])

    def test_search_cache_round_trip_and_input_signature(self):
        import numpy as np
        sys.path.insert(0, str(ROOT/'Role01'))
        from refresh_search import build_index, load_index, signature
        class Encoder:
            def encode(self, documents, **kwargs):
                return np.ones((len(documents), 3))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = dict(file_id='F001', filename='sample.txt', extracted_text='hello', path='dataset/files/sample.txt')
            for name in ('texts.csv', 'metadata.csv'):
                with (root/name).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=row)
                    writer.writeheader(); writer.writerow(row)
            build_index(root/'texts.csv', root/'metadata.csv', root/'index', encoder=Encoder())
            info, embeddings = load_index(root/'index')
            self.assertEqual(embeddings.shape, (1, 3))
            self.assertEqual(info['chunks'][0]['file_id'], 'F001')
            before = signature(root/'texts.csv', root/'metadata.csv')
            with (root/'metadata.csv').open('a') as stream:
                stream.write('\n')
            self.assertNotEqual(before, signature(root/'texts.csv', root/'metadata.csv'))


if __name__ == '__main__':
    unittest.main()
