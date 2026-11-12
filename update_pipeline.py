
"""파일 목록 갱신 → 텍스트 추출 → AI 설명 생성 → 증분 임베딩 갱신.

실행: 프로젝트 루트에서 python update_pipeline.py
또는 어느 폴더에서든 이 파일의 경로를 지정하여 실행.
"""
from pathlib import Path
import subprocess
import sys

PROJECT_DIR = Path(__file__).resolve().parent

# 1. 순서대로 실행할 작업
STEPS = [
    ("파일 목록 갱신", PROJECT_DIR / "Role01" / "file_reload_append_only.py", []),
    ("파일 내용 추출", PROJECT_DIR / "Role01" / "extract_content.py", []),
    ("AI 설명 생성", PROJECT_DIR / "Role02" / "description_generator.py", []),
    ("증분 임베딩 갱신", PROJECT_DIR / "Role01" / "refresh_search.py", ["--build-index"]),
]


def main():
    # 2. 각 작업을 순서대로 실행
    for number, (name, script, args) in enumerate(STEPS, start=1):
        print(f"\n[{number}/{len(STEPS)}] {name}", flush=True)

        if not script.is_file():
            print(f"오류: 스크립트를 찾을 수 없습니다: {script}", file=sys.stderr)
            sys.exit(1)

        # 3. 파이썬 파일 실행
        result = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=script.parent
        )

        # 4. 오류가 발생하면 다음 단계 실행하지 않음
        if result.returncode != 0:
            print(
                f"\n중단: '{name}' 단계 실패 (종료 코드 {result.returncode})",
                file=sys.stderr
            )
            sys.exit(result.returncode)

    print("\n완료! 메타데이터, 텍스트, AI 설명, 검색 임베딩 갱신 성공.")
    print("AI 설명:", PROJECT_DIR / "Role02" / "metadata_description_generated.csv")
    print("검색 인덱스:", PROJECT_DIR / "Role01" / "search_index")


if __name__ == "__main__":
    main()

