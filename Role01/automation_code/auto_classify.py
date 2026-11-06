import os
import sys
import json
import subprocess
from pathlib import Path

import pandas as pd

# 1. 폴더 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
ROLE02_DIR = PROJECT_DIR / "Role02"

METADATA_CSV = BASE_DIR / "metadata.csv"
TEXT_CSV = BASE_DIR / "extracted_text.csv"
OUTPUT_CSV = BASE_DIR / "auto_classification_results.csv"


# 2. Role02 분류기 실행
def run_classifier(script_name, file_id):

    script_path = ROLE02_DIR / script_name

    command = [
        sys.executable,
        str(script_path),
        "--csv", str(TEXT_CSV),
        "--file-id", file_id,
        "--json"
    ]

    result = subprocess.run(
        command,
        cwd=ROLE02_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    # JSON 결과를 파이썬 딕셔너리로 변환
    return json.loads(result.stdout)


# 3. 메타데이터와 추출 결과 읽기
metadata = pd.read_csv(
    METADATA_CSV,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

texts = pd.read_csv(
    TEXT_CSV,
    dtype=str,
    keep_default_na=False,
    encoding="utf-8-sig"
)

# 추출 성공한 파일만 분류
texts = texts[
    texts["extraction_status"] == "success"
]

# 기존 예측 결과 읽기
if OUTPUT_CSV.exists():
    old_results = pd.read_csv(
        OUTPUT_CSV,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig"
    )
else:
    old_results = pd.DataFrame()

# 이미 처리한 파일 ID
completed_ids = set()

if "file_id" in old_results.columns:
    completed_ids = set(old_results["file_id"])

# 새 결과를 저장할 리스트
results = []


# 4. 분류 시작
for _, row in metadata.iterrows():

    file_id = str(row["file_id"])
    filename = str(row["filename"])

    # 이전에 예측한 파일은 건너뛰기
    if file_id in completed_ids:
        continue

    # 추출된 텍스트가 없으면 건너뛰기
    matched = texts[texts["file_id"] == file_id]

    if matched.empty:
        continue

    # 이미 수동 라벨이 있는지 확인
    project = str(row["project"]).strip()
    role = str(row["role"]).strip()

    # 둘 다 있으면 분류할 필요 없음
    if project and role:
        continue

    print(f"\n분류 중: {file_id} {filename}")

    try:
        project_result = None
        role_result = None

        # project가 비어 있을 때만 예측
        if not project:
            project_result = run_classifier(
                "classify_new_file.py",
                file_id
            )

        # role이 비어 있을 때만 예측
        if not role:
            role_result = run_classifier(
                "classify_role.py",
                file_id
            )

        # 예측 결과 가져오기
        predicted_project = project
        predicted_role = role

        project_confidence = ""
        role_confidence = ""

        needs_confirmation = False

        if project_result is not None:
            predicted_project = project_result["project"]
            project_confidence = project_result["confidence"]

            if project_result["needs_confirmation"]:
                needs_confirmation = True

        if role_result is not None:
            predicted_role = role_result["role"]
            role_confidence = role_result["confidence"]

            if role_result["needs_confirmation"]:
                needs_confirmation = True

        # 결과 저장
        results.append({
            "file_id": file_id,
            "filename": filename,
            "project": predicted_project,
            "role": predicted_role,
            "project_confidence": project_confidence,
            "role_confidence": role_confidence,
            "needs_confirmation": needs_confirmation
        })

        print("프로젝트:", predicted_project)
        print("자료 유형:", predicted_role)
        print("확인 필요:", needs_confirmation)

    except Exception as e:
        print(f"[오류] {file_id}: {e}")


# 5. 기존 예측 결과와 합치기
new_results = pd.DataFrame(results)

if not old_results.empty:
    final_results = pd.concat(
        [old_results, new_results],
        ignore_index=True
    )
else:
    final_results = new_results

# 결과가 있을 때만 저장
if not final_results.empty:
    final_results.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

print("\n자동 분류 완료!")
print("이번 실행에서 새로 분류한 파일:", len(results))
print("저장 위치:", OUTPUT_CSV)
