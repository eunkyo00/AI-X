"""Adapt Role01's search engine to the existing gui-v1 contract."""
import importlib.util
import threading
import csv
import base64
import re
import sys
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
        # Role01 imports its sibling refresh_search module.
        sys.path.insert(0, str(Path(engine_dir).resolve()))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        self.engine = None
        self.engine_factory = module.SearchEngine
        self.engine_dir = Path(engine_dir)
        self.catalog = {}
        self.refresh_catalog()

    def content(self, file_id):
        path = self.originals.get(file_id)
        root = self.original_root
        allowed = [root]
        if hasattr(self, 'source_root'):
            allowed.append(self.source_root)
        if path is None or not any(path.resolve().is_relative_to(base) for base in allowed) or not path.is_file():
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


    @property
    def index_ready(self):
        return not (self.engine_dir.parent/'.update-data.lock').exists() and (
            self.engine is not None or (self.engine_dir/'search_index/index.json').exists())

    def refresh_catalog(self):
        if (self.engine_dir.parent/'.update-data.lock').exists():
            return
        def read(path):
            if not path.is_file():
                return {}
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            ids = [row['file_id'] for row in rows]
            if len(set(ids)) != len(ids):
                raise ValueError(f'{path.name}: file_id가 중복되어 있습니다.')
            return {row['file_id']: row for row in rows}

        extracted = read(self.engine_dir/'extracted_text.csv')
        metadata = read(self.engine_dir/'metadata.csv')
        descriptions = read(self.engine_dir.parent/'Role02/metadata_description_generated.csv')
        classifications = read(self.engine_dir.parent/'Role02/metadata_classification_generated.csv')
        catalog = {}
        for fid, base in (metadata or extracted).items():
            row = {**extracted.get(fid, {}), **base}
            description = descriptions.get(fid, {}).get('description', '')
            if description.strip():
                row['description'] = description
            prediction = classifications.get(fid, {})
            for field in ('project', 'role'):
                confirmed = str(prediction.get(field+'_needs_confirmation', '')).lower() in {'false', '0', 'no'}
                if not row.get(field, '').strip() and confirmed:
                    row[field] = prediction.get('predicted_'+field, '')
            item = self.file(row)
            item.update({key: prediction.get(key, '') for key in (
                'activity_at', 'time_source', 'year_month', 'quarter', 'half_year', 'season')})
            item['classification'] = prediction
            catalog[fid] = item
        self.catalog = catalog
        self.original_root = (self.engine_dir/'originals').resolve()
        self.source_root = (self.engine_dir/'dataset/files').resolve()
        self.originals = {}
        for fid, item in catalog.items():
            candidate = original_path(self.engine_dir, fid, item['name'])
            if not candidate.is_file():
                relative = item['path'].split('dataset/files/', 1)
                if len(relative) == 2:
                    candidate = self.source_root/relative[1]
            if (candidate.is_file() and any(candidate.resolve().is_relative_to(base)
                                          for base in (self.original_root, self.source_root))):
                self.originals[fid] = candidate
                item['content_available'] = True

    def list_files(self):
        with self.lock:
            self.refresh_catalog()
            return list(self.catalog.values())

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
                'project': str(row.get('project', '')),
                'size': size, 'modified_at': modified, 'index_status': 'ready' if row.get('extraction_status', 'success') == 'success' else 'unsupported', 'evidence': [],
                'content_available': False, 'relations_available': False}

    def search(self, query):
        # A single model instance is shared by HTTP worker threads.
        with self.lock:
            if hasattr(self, 'engine_dir'):
                self.refresh_catalog()
                if not any(row['index_status'] == 'ready' for row in self.catalog.values()):
                    return {'files': [], 'relations': []}
            if self.engine is None:
                self.engine = self.engine_factory()
            results = self.engine.search_files(query, top_k=5)
            if not hasattr(self, "engine_dir"):
                self.catalog = {str(row["file_id"]): self.file(row)
                                for row in self.engine.df.to_dict("records")}
            return {'files': [{**self.catalog[result['file_id']],
                           'score': result['score'], 'excerpt': result['chunk_text']}
                          for result in results], 'relations': []}
