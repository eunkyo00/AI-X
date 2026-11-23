from pathlib import Path
import hashlib
import json
import os
import pandas as pd
import requests

# 1. 기본 설정
MODEL_NAME = "qwen3.5:4b"
OLLAMA_URL = "http://localhost:11434/api/generate"
PROJECT_DIR = Path(__file__).resolve().parent.parent
METADATA_PATH = PROJECT_DIR / "Role01" / "metadata.csv"
TEXT_PATH = PROJECT_DIR / "Role01" / "extracted_text.csv"
MERGED_PATH = PROJECT_DIR / "Role02" / "metadata_description_merged.csv"
OUTPUT_PATH = PROJECT_DIR / "Role02" / "metadata_description_generated.csv"
HASH_PATH = PROJECT_DIR / "Role02" / "description_hashes.json"


def read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def check_ollama():
    print("Ollama 연결 확인 중...")
    response = requests.get("http://localhost:11434/api/tags", timeout=10)
    response.raise_for_status()
    models = [item["name"] for item in response.json()["models"]]
    if MODEL_NAME not in models:
        raise RuntimeError(f"{MODEL_NAME} 모델이 설치되어 있지 않습니다.")
    print("Ollama 연결 성공:", MODEL_NAME)


def generate_description(filename, extracted_text):
    text = extracted_text[:4000]
    prompt = f"""다음 파일의 이름과 내용을 참고하여
이 파일이 무엇에 관한 파일인지 한국어로 설명하세요.

조건:
- 1~2문장으로 작성
- 파일의 주요 내용과 목적을 설명
- 추측하거나 없는 내용을 만들어내지 말 것
- 자연스러운 한국어로 작성
- 설명 문장만 출력

파일명: {filename}

파일 내용:
{text}
"""
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False,
              "think": False, "options": {"temperature": 0, "num_predict": 160}},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def content_hash(text):
    # 설명 생성에 실제로 사용한 본문 기준
    return hashlib.sha256(text[:4000].encode("utf-8")).hexdigest()


def load_hashes():
    if not HASH_PATH.exists():
        return {}, True
    with open(HASH_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("description_hashes.json 형식이 잘못되었습니다.")
    return data, False


def save_hashes(hashes):
    HASH_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = HASH_PATH.with_suffix(".json.tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)
    os.replace(temp, HASH_PATH)


def save_result(result):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT_PATH.with_suffix(".csv.tmp")
    result.to_csv(temp, index=False, encoding="utf-8-sig")
    os.replace(temp, OUTPUT_PATH)


def main():
    metadata = read_csv(METADATA_PATH)
    extracted = read_csv(TEXT_PATH)
    if not metadata["file_id"].is_unique or not extracted["file_id"].is_unique:
        raise ValueError("file_id가 중복되어 있습니다.")
    if not {"file_id", "filename", "description"}.issubset(metadata.columns):
        raise ValueError("metadata.csv 필수 열이 없습니다.")
    if not {"file_id", "extracted_text"}.issubset(extracted.columns):
        raise ValueError("extracted_text.csv 필수 열이 없습니다.")

    result = metadata.copy(deep=True)
    previous = None
    if OUTPUT_PATH.exists():
        previous = read_csv(OUTPUT_PATH)
        print("이전 자동 생성 결과를 불러왔습니다.")
    elif MERGED_PATH.exists():
        previous = read_csv(MERGED_PATH)
        print("기존 병합 결과를 불러왔습니다.")

    old_desc = {}
    if previous is not None:
        if not previous["file_id"].is_unique:
            raise ValueError("이전 결과의 file_id가 중복되어 있습니다.")
        old_desc = previous.set_index("file_id")["description"].to_dict()

    text_map = extracted.set_index("file_id")["extracted_text"].to_dict()
    saved_hashes, first_run = load_hashes()
    if first_run:
        print("최초 실행: 기존 설명을 유지하면서 현재 본문 해시를 등록합니다.")

    next_hashes = {}
    pending = []
    reused = 0
    protected = 0
    skipped = 0

    for index, row in result.iterrows():
        file_id = row["file_id"]
        filename = row["filename"]
        original_description = row["description"].strip()
        text = text_map.get(file_id, "")
        old_description = old_desc.get(file_id, "").strip()
        new_hash = content_hash(text) if text.strip() else None
        old_hash = saved_hashes.get(file_id)

        # 수동 설명은 절대 자동 덮어쓰지 않음
        if original_description:
            protected += 1
            if new_hash:
                next_hashes[file_id] = new_hash
            continue

        if not text.strip():
            if old_description:
                result.at[index, "description"] = old_description
                reused += 1
            skipped += 1
            if old_hash:
                next_hashes[file_id] = old_hash
            continue

        # 최초 실행에는 이전 설명을 기준점으로 삼고 해시만 등록
        if old_description and (first_run or old_hash == new_hash):
            result.at[index, "description"] = old_description
            next_hashes[file_id] = new_hash
            reused += 1
            continue

        # 해시가 없거나 내용이 달라졌다면 새 설명 생성
        pending.append((index, file_id, filename, text, new_hash,
                        "수정" if old_description else "신규"))
        if old_description:
            result.at[index, "description"] = old_description
        if old_hash:
            next_hashes[file_id] = old_hash

    print("기존 description 재사용:", reused, "개")
    print("수동 description 보호:", protected, "개")
    print("생성/재생성 대상:", len(pending), "개")

    success = 0
    if pending:
        check_ollama()

    for index, file_id, filename, text, new_hash, kind in pending:
        try:
            description = generate_description(filename, text)
            if not description:
                print(file_id, "빈 응답 → 기존 설명 유지")
                continue
            result.at[index, "description"] = description
            next_hashes[file_id] = new_hash
            success += 1
            print(file_id, kind, "description 생성 완료")
            if success % 5 == 0:
                save_result(result)
                save_hashes(next_hashes)
                print("중간 저장 완료:", success, "개")
        except Exception as e:
            print(file_id, "오류:", e)

    for col in metadata.columns:
        if col != "description":
            assert result[col].equals(metadata[col])
    original_filled = metadata["description"].str.strip() != ""
    assert result.loc[original_filled, "description"].equals(
        metadata.loc[original_filled, "description"]
    )

    save_result(result)
    save_hashes(next_hashes)
    print("\n작업 완료!")
    print("전체 파일:", len(result))
    print("description 작성 완료:", result["description"].str.strip().ne("").sum())
    print("description 미작성:", result["description"].str.strip().eq("").sum())
    print("이번 실행 생성/재생성:", success)
    print("본문 없는 파일:", skipped)
    print("저장 위치:", OUTPUT_PATH)
    print("해시 저장 위치:", HASH_PATH)


if __name__ == "__main__":
    main()


