from pathlib import Path, PurePosixPath
from collections import Counter
import re
import posixpath
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# CSV 세 개를 같은 폴더에 두고 실행하세요.
BASE_DIR = Path(__file__).resolve().parent
METADATA_CSV = BASE_DIR / 'metadata.csv'
TEXT_CSV = BASE_DIR / 'extracted_text.csv'
OUTPUT_CSV = BASE_DIR / 'file_relations.csv'

# 조정 가능한 기준값. 처음에는 기본값으로 실행하세요.
SEMANTIC_THRESHOLD = 0.36
MAX_SEMANTIC_PER_FILE = 3
MAX_SAME_FOLDER_FILES = 10

metadata = pd.read_csv(METADATA_CSV, dtype=str, keep_default_na=False, encoding='utf-8-sig')
texts = pd.read_csv(TEXT_CSV, dtype=str, keep_default_na=False, encoding='utf-8-sig')
for col in ('file_id', 'filename', 'path'):
    if col not in metadata.columns:
        raise ValueError(f'metadata.csv에 {col} 열이 없습니다.')
for col in ('file_id', 'extracted_text'):
    if col not in texts.columns:
        raise ValueError(f'extracted_text.csv에 {col} 열이 없습니다.')

metadata = metadata.drop_duplicates('file_id').copy()
texts = texts.drop_duplicates('file_id').copy()
files = metadata.merge(texts[['file_id', 'extracted_text']], on='file_id', how='left')
files['extracted_text'] = files['extracted_text'].fillna('')
files['norm_path'] = files['path'].str.replace('\\', '/', regex=False).str.casefold().str.strip()
files['folder'] = files['norm_path'].map(posixpath.dirname)
files['norm_filename'] = files['filename'].str.casefold().str.strip()
files['extension'] = files['filename'].map(lambda x: Path(x).suffix.lower())

records = files.to_dict('records')
by_path = {r['norm_path']: r for r in records}
by_name = {}
for r in records:
    by_name.setdefault(r['norm_filename'], []).append(r)

relations = {}
def add_relation(source, target, kind, weight, evidence):
    if source == target:
        return
    key = (source, target, kind)
    value = dict(source_file_id=source, target_file_id=target,
                 relation_type=kind, weight=round(float(weight), 3), evidence=evidence)
    if key not in relations or weight > relations[key]['weight']:
        relations[key] = value

# 1. 파일명/경로를 명시한 참조 탐지
# Python, R, ipynb의 문자열과 Markdown/PDF 텍스트에 포함된 경로를 탐지합니다.
# 단, 코드 실행 여부를 증명하는 것은 아닙니다.
EXTS = r'(?:csv|tsv|xlsx|xls|json|txt|py|r|ipynb|pdf|md|pptx|docx)'
# 경로에 공백이 들어갈 수 있으므로 따옴표/백틱/괄호 기준으로 추출
quoted = re.compile(r'''["'`](.{1,350}?\.(?:csv|tsv|xlsx|xls|json|txt|py|r|ipynb|pdf|md|pptx|docx))["'`]''', re.I)
markdown_link = re.compile(r'\]\(([^)\s]+\.' + EXTS + r')\)', re.I)

for source in records:
    content = source['extracted_text']
    candidates = [m.group(1) for m in quoted.finditer(content)]
    candidates += [m.group(1) for m in markdown_link.finditer(content)]
    for raw in set(candidates):
        candidate = raw.strip().replace('\\', '/').split('?', 1)[0].casefold()
        if '://' in candidate or candidate.startswith(('http:', 'https:')):
            continue
        name = posixpath.basename(candidate)
        matches = by_name.get(name, [])
        if not matches:
            continue  # 참조된 파일이 데이터셋에 없을 수 있습니다.

        # 상대경로를 참조한 파일의 폴더 기준으로 해석
        expected = posixpath.normpath(posixpath.join(source['folder'], candidate))
        resolved = by_path.get(expected)
        if resolved is not None:
            add_relation(source['file_id'], resolved['file_id'], 'references', 1.0,
                         f'파일 경로 참조: {raw}')
            continue

        # 경로가 명시됐지만 위치가 다르면 잘못된 연결을 피함
        if '/' in candidate:
            continue

        # 파일명만 있고 같은 폴더에 유일한 대상이 있을 때
        local = [r for r in matches if r['folder'] == source['folder']]
        if len(local) == 1:
            add_relation(source['file_id'], local[0]['file_id'], 'references', 0.95,
                         f'동일 폴더 파일명 참조: {raw}')
        elif len(matches) == 1:
            # 폴더 밖 유일한 파일명은 '후보'로 낮은 점수로 연결
            add_relation(source['file_id'], matches[0]['file_id'], 'reference_candidate', 0.5,
                         f'파일명 언급(경로 미확인): {raw}')

# 2. 파일명/내용의 유사성을 이용한 후보 관계
# TF-IDF는 새 모델 다운로드가 필요 없는 가벼운 첫 단계입니다.
# 'semantic_related'가 아니라 'content_similar'로 표기하여 의미 검색 모델과 구분합니다.
# 긴 PDF의 본문을 그대로 쓰면 공통 표현이 과도하게 반영되므로 일부만 사용합니다.
texts_for_similarity = []
for r in records:
    filename = Path(r['filename']).stem.replace('_', ' ').replace('-', ' ')
    description = r.get('description', '')
    project = r.get('project', '')
    body = r['extracted_text'][:5000]
    texts_for_similarity.append((filename + ' ') * 3 + (description + ' ') * 2 + project + ' ' + body)

if len(records) >= 2:
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 4), min_df=1,
                                 max_features=30000, sublinear_tf=True)
    matrix = vectorizer.fit_transform(texts_for_similarity)
    sim = cosine_similarity(matrix)
    for i, source in enumerate(records):
        candidates = []
        for j, target in enumerate(records):
            if i == j:
                continue
            # 같은 형식의 일반 강의자료가 서로 연결되는 것을 줄이고,
            # PDF ↔ R / ipynb ↔ CSV 등의 교차 형식 관계를 우선합니다.
            if source['extension'] == target['extension']:
                continue
            score = float(sim[i, j])
            if score >= SEMANTIC_THRESHOLD:
                candidates.append((score, target))
        candidates.sort(key=lambda x: x[0], reverse=True)
        for score, target in candidates[:MAX_SEMANTIC_PER_FILE]:
            add_relation(source['file_id'], target['file_id'], 'content_similar',
                         score, f'파일명·설명·추출본문 TF-IDF 유사도: {score:.3f}')

# 3. 동일 폴더: 강한 사용 관계가 아니라 보조 맥락
for folder, group in files.groupby('folder'):
    if not folder or not (2 <= len(group) <= MAX_SAME_FOLDER_FILES):
        continue
    ids = group['file_id'].tolist()
    for a in ids:
        for b in ids:
            if a != b:
                add_relation(a, b, 'same_folder', 0.2, f'동일 폴더: {folder}')

columns = ['source_file_id', 'target_file_id', 'relation_type', 'weight', 'evidence']
result = pd.DataFrame(list(relations.values()), columns=columns)
if not result.empty:
    result = result.sort_values(['source_file_id', 'relation_type', 'target_file_id'])
result.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
print(f'전체 파일: {len(files)}개 / 관계: {len(result)}개')
print(result['relation_type'].value_counts().to_string() if len(result) else '관계 없음')
print(f'저장: {OUTPUT_CSV}')
