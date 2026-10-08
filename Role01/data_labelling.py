from pathlib import Path
from datetime import datetime
import pandas as pd

# 1. 데이터 폴더 위치 지정
DATA_DIR = Path("dataset/files/")

# 2. 검색 대상에서 제외할 확장자
#   현재는 이미지 파일을 제외
EXCLUDED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"
}

# 3. 파일 정보 수집
file_data = []

file_id = 1

for file_path in DATA_DIR.rglob("*"):

    # 폴더는 제외
    if not file_path.is_file():
        continue

    # 확장자 확인
    extension = file_path.suffix.lower()

    # 이미지 파일은 제외
    if extension in EXCLUDED_EXTENSIONS:
        continue

    # 파일 정보 가져오기
    stat = file_path.stat()

    file_data.append({
        "file_id": f"F{file_id:03d}",
        "filename": file_path.name,
        "extension": extension,
        "path": str(file_path),
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),

        # 아래 항목은 사람이 나중에 직접 입력
        "project": "",
        "role": "",
        "description": ""  # <--- 이 줄이 추가되었습니다!
    })

    file_id += 1

# 4. DataFrame으로 변환
df = pd.DataFrame(file_data)

# 5. 확인
print(f"총 {len(df)}개 파일을 찾았습니다.")
print(df)

# 6. CSV 파일로 저장 (utf-8-sig 사용)
df.to_csv("metadata.csv", index=False, encoding="utf-8-sig")

print("metadata.csv 저장 완료!")