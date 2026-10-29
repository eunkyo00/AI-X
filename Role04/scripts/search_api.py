"""Adapt Role01's search engine to the existing gui-v1 contract."""
import importlib.util
import threading
from datetime import datetime
from pathlib import Path


class SearchService:
    def __init__(self, engine_dir):
        self.lock = threading.Lock()
        source = Path(engine_dir) / 'search_engine.py'
        if not source.is_file():
            raise FileNotFoundError('검색 엔진이 없습니다. scripts/prepare_search.py를 먼저 실행하세요.')
        spec = importlib.util.spec_from_file_location('role01_search_engine', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.engine = module.SearchEngine()
        self.catalog = {str(row['file_id']): self.file(row) for row in self.engine.df.to_dict('records')}

    @staticmethod
    def file(row):
        modified = ''
        for fmt in ('%Y.%m.%d %H:%M', '%Y-%m-%d %H:%M:%S'):
            try:
                modified = datetime.strptime(str(row.get('modified_at', '')), fmt).isoformat()
                break
            except ValueError:
                pass
        try:
            size = int(row.get('size_bytes', ''))
        except (ValueError, TypeError):
            size = None
        return {'file_id': str(row['file_id']), 'name': str(row['filename']),
                'path': str(row.get('path', '')).replace('\\', '/'),
                'role': str(row.get('role', '')), 'summary': str(row.get('description', '')),
                'size': size, 'modified_at': modified, 'index_status': 'ready', 'evidence': [],
                'content_available': False, 'relations_available': False}

    def search(self, query):
        # A single model instance is shared by HTTP worker threads.
        with self.lock:
            results = self.engine.search_files(query, top_k=5)
        return {'files': [{**self.catalog[result['file_id']],
                           'score': result['score'], 'excerpt': result['chunk_text']}
                          for result in results], 'relations': []}
