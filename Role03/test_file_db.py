import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from file_db import build, code_references, get_file, get_relations, resolve_reference, validate


class FileDBTests(unittest.TestCase):
    def test_python_literals_comments_and_dynamic_paths(self):
        source = '# pd.read_csv("fake.csv")\npd.read_csv("input.csv")\ndf.to_csv("out.csv")\npd.read_csv(variable)\nopen("note.txt", "w")'
        refs = list(code_references(source, '.py'))
        self.assertEqual([(r[0], r[1]) for r in refs], [('input.csv', 'reads'), ('out.csv', 'writes'), ('note.txt', 'writes')])

    def test_r_reads_writes_and_comments(self):
        source = '# read.csv("fake.csv")\nx <- read.csv("in.csv") # read.csv("fake.csv")\nwrite.csv(x, file="out.csv")\nsaveRDS(x, "out.rds")\nfread(input="other.csv")'
        self.assertEqual([(r[0], r[1]) for r in code_references(source, '.r')], [('in.csv', 'reads'), ('out.csv', 'writes'), ('out.rds', 'writes'), ('other.csv', 'reads')])

    def test_same_names_not_silently_linked(self):
        source = {'file_id':'S', 'path':'dataset/files/a/code.py'}
        files = [{'file_id':'A','path':'dataset/files/a/in.csv','filename':'in.csv'}, {'file_id':'B','path':'dataset/files/b/in.csv','filename':'in.csv'}]
        self.assertEqual(resolve_reference(source, 'in.csv', files), ('A','resolved','exact_path'))
        self.assertEqual(resolve_reference(source, '../unknown/in.csv', files)[1], 'ambiguous')
        self.assertEqual(resolve_reference(source, 'absent.csv', files)[1], 'missing')

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            validate([{'file_id':'A'}, {'file_id':'A'}], [])

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
