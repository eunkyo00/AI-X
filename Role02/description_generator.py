
from pathlib import Path
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# 1. 기본 설정
MODEL_NAME = "Qwen/Qwen3-4B"

# Colab의 Google Drive 경로
PROJECT_DIR = Path("/content/drive/MyDrive/AI-X")

METADATA_PATH = PROJECT_DIR / "Role01" / "metadata.csv"
TEXT_PATH = PROJECT_DIR / "Role01" / "extracted_text.csv"

# 기존에 생성한 199개 설명
MERGED_PATH = (
    PROJECT_DIR / "Role02" / "metadata_description_merged.csv"
)

# 자동 생성 결과 저장
OUTPUT_PATH = (
    PROJECT_DIR / "colab_output" / "metadata_description_generated.csv"
)


# 2. CSV 읽기
def read_csv(path):
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False
    )


# 3. Qwen 모델 로딩
def load_model():
    print("Qwen 모델 로딩 중...")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,
        device_map="auto"
    )

    model.eval()
    return tokenizer, model


# 4. description 생성
def generate_description(filename, extracted_text, tokenizer, model):

    text = extracted_text[:4000]

    prompt = f"""
다음 파일의 이름과 내용을 참고하여
이 파일이 무엇에 관한 파일인지 한국어로 설명하세요.

조건:
- 1~2문장으로 작성
- 파일의 주요 내용과 목적을 설명
- 추측하거나 없는 내용을 만들어내지 말 것
- 자연스러운 한국어로 작성

파일명: {filename}

파일 내용:
{text}
"""

    messages = [{"role": "user", "content": prompt}]

    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
        return_tensors="pt",
        return_dict=True
    )

    inputs = inputs.to(model.device)
    input_ids = inputs["input_ids"]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=160,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id
        )

    generated = outputs[0][input_ids.shape[-1]:]

    return tokenizer.decode(
        generated,
        skip_special_tokens=True
    ).strip()


# 5. 기존 description 가져오기
def merge_existing_descriptions(metadata):

    result = metadata.copy(deep=True)

    # 이전 생성 결과를 우선 사용
    if OUTPUT_PATH.exists():
        previous = read_csv(OUTPUT_PATH)
        print("이전 자동 생성 결과를 불러왔습니다.")

    elif MERGED_PATH.exists():
        previous = read_csv(MERGED_PATH)
        print("기존 병합 결과를 불러왔습니다.")

    else:
        print("기존 생성 결과가 없습니다.")
        return result

    # file_id 중복 확인
    assert result["file_id"].is_unique
    assert previous["file_id"].is_unique

    description_map = previous.set_index("file_id")[
        "description"
    ].to_dict()

    reused = 0

    for index, row in result.iterrows():

        # 원본 description이 있으면 그대로 유지
        if row["description"].strip():
            continue

        file_id = row["file_id"]
        old_description = description_map.get(file_id, "")

        if old_description.strip():
            result.at[index, "description"] = old_description
            reused += 1

    print("기존 description 재사용:", reused, "개")
    return result


# 6. 생성 결과 저장
def save_result(result):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig"
    )


# 7. 빈 description 자동 생성
def fill_descriptions(result, extracted, tokenizer, model):

    text_map = extracted.set_index("file_id")[
        "extracted_text"
    ].to_dict()

    empty_rows = result[
        result["description"].str.strip() == ""
    ]

    print("새로 생성할 description:", len(empty_rows), "개")

    success = 0

    for index, row in empty_rows.iterrows():

        file_id = row["file_id"]
        filename = row["filename"]
        text = text_map.get(file_id, "")

        if not text.strip():
            print(file_id, "본문 없음 → 건너뜀")
            continue

        try:
            description = generate_description(
                filename, text, tokenizer, model
            )

            if description.strip():
                result.at[index, "description"] = description
                success += 1
                print(file_id, "생성 완료")

                # 5개 생성할 때마다 저장
                if success % 5 == 0:
                    save_result(result)
                    print("중간 저장 완료:", success, "개")

        except Exception as e:
            print(file_id, "오류:", e)

    return result


# 8. 실행
def main():

    # 원본 CSV 읽기
    metadata = read_csv(METADATA_PATH)
    extracted = read_csv(TEXT_PATH)

    # 기존 description 재사용
    result = merge_existing_descriptions(metadata)

    # 새로 생성해야 하는 파일 수
    empty_count = result["description"].str.strip().eq("").sum()

    if empty_count == 0:
        print("새로 생성할 description이 없습니다.")

    else:
        # 생성 대상이 있을 때만 모델 로딩
        tokenizer, model = load_model()

        result = fill_descriptions(
            result, extracted, tokenizer, model
        )

    # 기존 데이터 보존 확인
    for col in metadata.columns:
        if col != "description":
            assert result[col].equals(metadata[col])

    original_filled = metadata["description"].str.strip() != ""

    assert result.loc[original_filled, "description"].equals(
        metadata.loc[original_filled, "description"]
    )

    # 최종 결과 저장
    save_result(result)

    print("\n작업 완료!")
    print("전체 파일:", len(result))
    print(
        "description 작성 완료:",
        result["description"].str.strip().ne("").sum()
    )
    print(
        "description 미작성:",
        result["description"].str.strip().eq("").sum()
    )
    print("저장 위치:", OUTPUT_PATH)


if __name__ == "__main__":
    main()

