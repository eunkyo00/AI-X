from pathlib import Path
import ast
import re
import pandas as pd

# 1. 파일 위치
BASE_DIR = Path(__file__).resolve().parent
METADATA_CSV = BASE_DIR / "metadata.csv"
TEXT_CSV = BASE_DIR / "extracted_text.csv"
OUTPUT_CSV = BASE_DIR / "file_relations.csv"

# 동일 폴더 관계가 너무 많이 생성되지 않도록 제한
MAX_SAME_FOLDER_FILES = 10

# 2. CSV 불러오기
metadata = pd.read_csv(METADATA_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
texts = pd.read_csv(TEXT_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")

for col in ["file_id", "filename", "path"]:
    if col not in metadata.columns:
        raise ValueError(f"metadata.csv에 '{col}' 열이 없습니다.")
for col in ["file_id", "extracted_text"]:
    if col not in texts.columns:
        raise ValueError(f"extracted_text.csv에 '{col}' 열이 없습니다.")

metadata = metadata.drop_duplicates("file_id").copy()
texts = texts.drop_duplicates("file_id").copy()

# Windows 경로와 Linux 경로를 같은 방식으로 비교
metadata["normalized_path"] = metadata["path"].str.replace("\\", "/", regex=False).str.strip().str.casefold()
metadata["folder"] = metadata["normalized_path"].str.rsplit("/", n=1).str[0]
metadata["normalized_filename"] = metadata["filename"].str.strip().str.casefold()

files = metadata.merge(texts[["file_id", "extracted_text"]], on="file_id", how="left")
files["extracted_text"] = files["extracted_text"].fillna("")

# 3. 관계 저장 함수
relations = {}

def add_relation(source_id, target_id, relation_type, weight, evidence):
    if source_id == target_id:
        return
    key = (source_id, target_id, relation_type)
    relations[key] = {
        "source_file_id": source_id,
        "target_file_id": target_id,
        "relation_type": relation_type,
        "weight": weight,
        "evidence": evidence,
    }

# 4. 코드에서 문자열로 작성된 파일 참조 찾기
# 예: pd.read_csv('birds.csv'), open('data.txt'), read_excel('sample.xlsx')
# 주의: 정적 텍스트 분석이므로 실제 실행 여부까지 증명하지는 않음
FILE_EXTENSIONS = (".csv", ".xlsx", ".xls", ".json", ".txt", ".py", ".r", ".ipynb", ".pdf")

# 인용부호 안에 적힌 파일명/경로 후보만 찾음
quoted_strings = re.compile(r"(['\"])([^'\"\r\n]{1,300})\1")

for _, source in files.iterrows():
    source_id = source["file_id"]
    source_text = source["extracted_text"]
    if not source_text:
        continue

    candidates = set()
    for match in quoted_strings.finditer(source_text):
        value = match.group(2).strip().replace("\\", "/").casefold()
        if value.endswith(FILE_EXTENSIONS):
            candidates.add(value)

    for candidate in candidates:
        candidate_name = candidate.rsplit("/", 1)[-1]
        matches = files[files["normalized_filename"] == candidate_name]
        if matches.empty:
            continue

        # 같은 이름의 파일이 여럿이면 같은 폴더의 파일만 연결
        if len(matches) > 1:
            matches = matches[matches["folder"] == source["folder"]]
        if len(matches) != 1:
            continue

        target = matches.iloc[0]
        # 파일명만 같은 다른 폴더의 파일을 잘못 연결하지 않도록
        # 단순 파일명 참조는 동일 폴더에 있을 때만 확정
        if "/" not in candidate and source["folder"] != target["folder"]:
            continue
        # 경로를 명시한 경우, 실제 저장 경로 끝부분과 일치해야 함
        if "/" in candidate and not target["normalized_path"].endswith(candidate):
            continue

        add_relation(source_id, target["file_id"], "references", 1.0, f"텍스트에 파일 참조: {candidate}")

# 5. 동일 폴더 관계 (약한 관계)
for folder, group in files.groupby("folder"):
    if not folder or len(group) < 2 or len(group) > MAX_SAME_FOLDER_FILES:
        continue
    ids = group["file_id"].tolist()
    for source_id in ids:
        for target_id in ids:
            if source_id != target_id:
                add_relation(source_id, target_id, "same_folder", 0.2, f"동일 폴더: {folder}")

# 6. CSV 저장
columns = ["source_file_id", "target_file_id", "relation_type", "weight", "evidence"]
result = pd.DataFrame(list(relations.values()), columns=columns)
if not result.empty:
    result = result.sort_values(["source_file_id", "relation_type", "target_file_id"])
result.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

print(f"전체 파일 수: {len(files)}")
print(f"생성된 관계 수: {len(result)}")
if not result.empty:
    print(result["relation_type"].value_counts().to_string())
print(f"저장 완료: {OUTPUT_CSV}")
