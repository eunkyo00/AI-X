from pathlib import Path
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# 1. 기본 설정
MODEL_NAME = "Qwen/Qwen3-4B"

# CSV 파일 경로
PROJECT_DIR = Path("/content/drive/MyDrive/AI-X")
METADATA_PATH = PROJECT_DIR / "Role01" / "metadata.csv"
TEXT_PATH = PROJECT_DIR / "Role01" / "extracted_text.csv"
OUTPUT_PATH = PROJECT_DIR / "colab_output" / "metadata_description_generated.csv"


# 2. Qwen 모델 불러오기
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


# 3. 파일 설명 생성
def generate_description(filename, extracted_text, tokenizer, model):

    # 긴 파일은 앞부분 4000자만 사용
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

    messages = [
        {"role": "user", "content": prompt}
    ]

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

    description = tokenizer.decode(
        generated,
        skip_special_tokens=True
    ).strip()

    return description


# 4. CSV 데이터 읽기
def load_data():

    metadata = pd.read_csv(
        METADATA_PATH,
        dtype=str,
        keep_default_na=False
    )

    extracted = pd.read_csv(
        TEXT_PATH,
        dtype=str,
        keep_default_na=False
    )

    return metadata, extracted


# 5. 빈 description 자동 생성
def fill_descriptions(metadata, extracted, tokenizer, model):

    result = metadata.copy(deep=True)

    text_map = extracted.set_index("file_id")["extracted_text"].to_dict()

    empty_rows = result[
        result["description"].str.strip() == ""
    ]

    print("생성 대상:", len(empty_rows))

    success = 0

    for index, row in empty_rows.iterrows():

        file_id = row["file_id"]
        filename = row["filename"]
        text = text_map.get(file_id, "")

        if not text.strip():
            print(file_id, "본문 없음")
            continue

        try:
            description = generate_description(
                filename, text, tokenizer, model
            )

            if description.strip():
                result.at[index, "description"] = description
                success += 1
                print(file_id, "생성 완료")

        except Exception as e:
            print(file_id, "오류:", e)

        # 5개 생성할 때마다 저장
        if success > 0 and success % 5 == 0:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            result.to_csv(
                OUTPUT_PATH,
                index=False,
                encoding="utf-8-sig"
            )

    return result


# 6. 실행
def main():

    metadata, extracted = load_data()

    tokenizer, model = load_model()

    result = fill_descriptions(
        metadata, extracted, tokenizer, model
    )

    # 기존 데이터 보존 확인
    for col in metadata.columns:
        if col != "description":
            assert result[col].equals(metadata[col])

    original_filled = metadata["description"].str.strip() != ""
    assert result.loc[original_filled, "description"].equals(
        metadata.loc[original_filled, "description"]
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    print("최종 저장 완료:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
