"""Adapt Role01's search engine to the existing gui-v1 contract."""
import importlib.util
import base64
import threading
import re
from datetime import datetime
from pathlib import Path


def original_path(engine_dir, file_id, filename):
    # Paths are derived from the trusted catalog, never from client-supplied paths.
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(file_id)):
        raise ValueError('잘못된 파일 ID입니다.')
    suffix = Path(str(filename)).suffix.lower()
    if suffix and not re.fullmatch(r'\.[a-z0-9]+', suffix):
        raise ValueError('잘못된 확장자입니다.')
    root = (Path(engine_dir) / 'originals').resolve()
    candidate = root / (str(file_id) + suffix)
    if not candidate.resolve().is_relative_to(root):
        raise ValueError('원본 폴더 밖의 경로입니다.')
    return candidate


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
        self.original_root = (Path(engine_dir) / 'originals').resolve()
        self.originals = {file_id: original_path(engine_dir, file_id, item['name']) for file_id, item in self.catalog.items()}
        for file_id, item in self.catalog.items():
            item['content_available'] = self.originals[file_id].is_file()

    def content(self, file_id):
        path = self.originals.get(file_id)
        root = self.original_root
        if path is None or not path.resolve().is_relative_to(root) or not path.is_file():
            raise FileNotFoundError('원본 파일이 없습니다. 데이터 준비 스크립트를 다시 실행하세요.')
        return path

    def preview_pdf(self, file_id, page=1):
        import pymupdf
        path = self.content(file_id)
        if path.suffix.lower() != '.pdf':
            raise ValueError('PDF 파일만 페이지 미리보기를 지원합니다.')
        with pymupdf.open(path) as document:
            if not 1 <= page <= len(document):
                raise ValueError('존재하지 않는 페이지입니다.')
            source = document[page - 1]
            scale = min(1.5, 1600 / max(source.rect.width, source.rect.height, 1))
            pixmap = source.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return {'page': page, 'page_count': len(document),
                    'image_base64': base64.b64encode(pixmap.tobytes('png')).decode('ascii')}

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
            self.catalog = {str(row["file_id"]): self.file(row)
                            for row in self.engine.df.to_dict("records")}
        return {'files': [{**self.catalog[result['file_id']],
                           'score': result['score'], 'excerpt': result['chunk_text']}
                          for result in results], 'relations': []}
