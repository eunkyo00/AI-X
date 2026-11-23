import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from file_db import build, code_references, document_references, get_file, get_relations, resolve_reference, validate
from audit_results import classify_reference


class FileDBTests(unittest.TestCase):
    def test_python_literals_comments_and_dynamic_paths(self):
        source = '# pd.read_csv("fake.csv")\npd.read_csv("input.csv")\ndf.to_csv("out.csv")\npd.read_csv(variable)\nopen("note.txt", "w")'
        refs = list(code_references(source, '.py'))
        self.assertEqual([(r[0], r[1]) for r in refs], [('input.csv', 'reads'), ('out.csv', 'writes'), ('note.txt', 'writes')])

    def test_r_reads_writes_and_comments(self):
        source = '# read.csv("fake.csv")\nx <- read.csv("in.csv") # read.csv("fake.csv")\nwrite.csv(x, file="out.csv")\nsaveRDS(x, "out.rds")\nfread(input="other.csv")'
        self.assertEqual([(r[0], r[1]) for r in code_references(source, '.r')], [('in.csv', 'reads'), ('out.csv', 'writes'), ('out.rds', 'writes'), ('other.csv', 'reads')])

    def test_python_multiline_and_keyword_output(self):
        source = 'df.to_csv(\n    path_or_buf="output.csv"\n)'
        refs = list(code_references(source, '.py'))
        self.assertEqual(refs, [('output.csv', 'writes', 1, source)])

    def test_same_names_not_silently_linked(self):
        source = {'file_id':'S', 'path':'dataset/files/a/code.py'}
        files = [{'file_id':'A','path':'dataset/files/a/in.csv','filename':'in.csv'}, {'file_id':'B','path':'dataset/files/b/in.csv','filename':'in.csv'}]
        self.assertEqual(resolve_reference(source, 'in.csv', files), ('A','resolved','exact_path'))
        self.assertEqual(resolve_reference(source, '../unknown/in.csv', files)[1], 'ambiguous')
        self.assertEqual(resolve_reference(source, 'absent.csv', files)[1], 'missing')

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            validate([{'file_id':'A'}, {'file_id':'A'}], [])

    def test_document_paths_unregistered_repeated_and_spaced_names(self):
        text = '참고 [자료](./data/in.csv), `없는 자료.pdf`, in.csv 및 in.csv\nhttps://example.org/web.pdf'
        refs = list(document_references(text, []))
        self.assertEqual([r[0] for r in refs], ['./data/in.csv', '없는 자료.pdf', 'in.csv', 'in.csv'])
        for ref, offset, evidence in refs:
            self.assertEqual(text[offset:offset+len(ref)], ref)
            self.assertIn(ref, evidence)

    def test_document_resolution_and_duplicate_paths(self):
        source = {'file_id': 'S', 'path': 'dataset/files/a/note.md'}
        files = [{'file_id': 'A', 'filename': 'in.csv', 'path': 'dataset/files/a/in.csv'}]
        self.assertEqual(resolve_reference(source, './in.csv', files)[0], 'A')
        self.assertEqual(resolve_reference(source, 'in.csv', files, filename_only=True)[1], 'ambiguous')
        self.assertEqual(resolve_reference(source, './absent.csv', files)[1], 'missing')
        files.append(dict(files[0], file_id='B'))
        self.assertEqual(resolve_reference(source, './in.csv', files)[1], 'ambiguous')

    def test_external_link_label_is_not_local_but_preview_image_is(self):
        text = '[`metadata.csv`](https://example.org/data.zip) [![preview](images/a.png)](https://example.org) `local.csv`'
        self.assertEqual([r[0] for r in document_references(text, [])], ['images/a.png', 'local.csv'])

    def test_tsv_recovery_is_saved_without_changing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root/'table.tsv'
            original.write_text('name\tvalue\n가\t1\n', encoding='utf-8')
            meta = dict(file_id='T', filename='table.tsv', path='dataset/files/table.tsv', extension='.tsv', size_bytes=str(original.stat().st_size), created_at='', modified_at='', project='', role='', description='')
            text = dict(meta, extracted_text='', extraction_status='unsupported_extension')
            for name, row in [('metadata.csv', meta), ('texts.csv', text)]:
                with (root/name).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=row); writer.writeheader(); writer.writerow(row)
            before = (root/'texts.csv').read_bytes()
            with patch('file_db.local_path', return_value=original):
                summary = build(root/'metadata.csv', root/'texts.csv', root/'out')
            stored = get_file(root/'out/files.sqlite3', 'T')
            self.assertEqual(summary['extraction_success'], 1)
            self.assertEqual(stored['extraction_status'], 'success')
            self.assertEqual(stored['extracted_text'], 'name | value\n가 | 1')
            self.assertEqual((root/'texts.csv').read_bytes(), before)

    def test_reference_audit_distinguishes_external_output_and_candidates(self):
        source = {'path': 'dataset/files/example/code.py'}
        row = dict(reference_path='https://example.org/data.csv', status='missing', relation_type='reads')
        self.assertEqual(classify_reference(row, source, {}, {})[0], 'external_url')
        self.assertEqual(classify_reference(dict(row, reference_path='/content/out.png', relation_type='writes'), source, {}, {})[0], 'output_reference')
        row['reference_path'] = 'input.csv'
        self.assertEqual(classify_reference(row, source, {}, {})[0], 'code_input_not_in_corpus')
        self.assertEqual(classify_reference(row, source, {'input.csv': ['local/input.csv']}, {})[0], 'local_filename_candidate')

    def test_document_evidence_database_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = dict(size_bytes='0', created_at='', modified_at='', project='', role='', description='')
            metadata = [dict(base, file_id='S', filename='note.md', path='dataset/files/a/note.md', extension='.md'),
                        dict(base, file_id='T', filename='in.csv', path='dataset/files/a/in.csv', extension='.csv')]
            texts = [dict(row, extracted_text='[입력](./in.csv) in.csv `missing.pdf`' if row['file_id']=='S' else '', extraction_status='success') for row in metadata]
            for name, rows in [('metadata.csv', metadata), ('texts.csv', texts)]:
                with (root/name).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
            for _ in range(2):
                summary = build(root/'metadata.csv', root/'texts.csv', root/'out')
                self.assertEqual([summary[k] for k in ('resolved', 'ambiguous', 'missing')], [1, 1, 1])
            relations = get_relations(root/'out/files.sqlite3', 'S')
            self.assertEqual(relations[0]['target_id'], 'T')
            self.assertTrue(all(r['evidence'] and r['evidence_location'] for r in relations))
            self.assertEqual(len(get_relations(root/'out/files.sqlite3', 'T')), 1)

    def test_database_round_trip_repeat_and_failed_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = dict(file_id='F001',filename='in.csv',path='dataset/files/example/in.csv',extension='.csv',size_bytes='5',created_at='2026-10-01',modified_at='2026-10-02',project='sample',role='input',description='test')
            text = dict(meta, extracted_text='a,b\n1,2',extraction_status='success')
            for name, row in [('metadata.csv', meta), ('extracted_text.csv', text)]:
                with (root/name).open('w',newline='') as stream:
                    writer = csv.DictWriter(stream,fieldnames=row.keys()); writer.writeheader(); writer.writerow(row)
            for _ in range(2):
                self.assertEqual(build(root/'metadata.csv',root/'extracted_text.csv',root/'out')['files'],1)
            db = root/'out/files.sqlite3'
            self.assertEqual(get_file(db,'F001')['extracted_text'],'a,b\n1,2')
            self.assertIsNone(get_file(db,'unknown'))
            self.assertEqual(get_relations(db,'F001'),[])
            with (root/'metadata.csv').open('a') as stream:
                stream.write('F001,in.csv\n')
            with self.assertRaises(ValueError):
                build(root/'metadata.csv',root/'extracted_text.csv',root/'out')
            self.assertEqual(get_file(db,'F001')['description'],'test')
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
