"""Regression checks for November backend joins, imports and folder contracts."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_gui_integration as fixtures
from search_api import load_module


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


class LatestTeamTests(unittest.TestCase):
    def test_predictions_join_by_id_and_preserve_manual_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            service = fixtures.AdapterTests.service(self, Path(directory))
            two = service.backend / 'Role02'
            write_csv(two / 'metadata_description_generated.csv', [
                dict(file_id='F002', description='second description'),
                dict(file_id='F001', description='first description')])
            write_csv(two / 'metadata_classification_generated.csv', [
                dict(file_id='F001', predicted_project='uncertain', project_needs_confirmation='True',
                     predicted_role='코드', role_needs_confirmation='False', activity_at='2026-04-10', time_source='modified_at'),
                dict(file_id='F002', predicted_project='통계', project_needs_confirmation='False',
                     predicted_role='자료', role_needs_confirmation='False', activity_at='', time_source='')])
            service._reload_catalog()
            self.assertEqual(service.catalog['F001']['summary'], 'first description')
            self.assertEqual(service.catalog['F001']['project'], '')
            self.assertEqual(service.catalog['F001']['role'], '코드')
            self.assertEqual(service.catalog['F002']['project'], '통계')
            self.assertEqual(service.catalog['F001']['time_source'], 'modified_at')
            with (service.engine_dir / 'metadata.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                row['project'] = '수동 과목'
            write_csv(service.engine_dir / 'metadata.csv', rows)
            service._reload_catalog()
            self.assertEqual(service.catalog['F002']['project'], '수동 과목')

    def test_v5_recommendations_replace_legacy_evidence_and_skip_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            service = fixtures.AdapterTests.service(self, Path(directory))
            write_csv(service.engine_dir / 'file_relations_v5.csv', [
                dict(source_file_id='F001', target_file_id='F002', evidence='동일 주차 파일'),
                dict(source_file_id='F001', target_file_id='F999', evidence='삭제된 파일')])
            links = service.search('first')['relations']
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]['evidence'], '동일 주차 파일')
            self.assertEqual(links[0]['certainty'], 'inferred')

    def test_staged_engine_imports_do_not_reuse_live_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('live', 'stage'):
                folder = root / name
                folder.mkdir()
                (folder / 'refresh_search.py').write_text(f"VALUE = '{name}'\n")
                (folder / 'search_engine.py').write_text('from refresh_search import VALUE\n')
            self.assertEqual(load_module(root/'live/search_engine.py', 'test_live').VALUE, 'live')
            self.assertEqual(load_module(root/'stage/search_engine.py', 'test_stage').VALUE, 'stage')
            self.assertEqual(load_module(root/'live/search_engine.py', 'test_live_again').VALUE, 'live')


if __name__ == '__main__':
    unittest.main()
