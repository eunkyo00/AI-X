"""파일 등록 → 추출 → 설명 → 프로젝트/Role/시간 분류 → 검색 인덱스 갱신."""

from pathlib import Path
import subprocess
import sys

PROJECT_DIR = Path(__file__).resolve().parent

STEPS = [
    ("파일 목록 갱신", PROJECT_DIR / "Role01" / "file_reload_append_only.py", []),
    ("파일 내용 추출", PROJECT_DIR / "Role01" / "extract_content.py", []),
    ("AI 설명 생성", PROJECT_DIR / "Role02" / "description_generator.py", []),
    ("프로젝트·Role·시간 자동 분류", PROJECT_DIR / "Role02" / "classify_metadata.py", []),
    ("증분 임베딩 갱신", PROJECT_DIR / "Role01" / "refresh_search.py", ["--build-index"]),
]


def main():
    for number, (name, script, args) in enumerate(STEPS, 1):
        print(f"\n[{number}/{len(STEPS)}] {name}", flush=True)

        if not script.is_file():
            print(f"오류: 스크립트를 찾을 수 없습니다: {script}", file=sys.stderr)
            sys.exit(1)

        result = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=script.parent
        )

        if result.returncode != 0:
            print(
                f"\n중단: '{name}' 단계 실패 (종료 코드 {result.returncode})",
                file=sys.stderr
            )
            sys.exit(result.returncode)

    print("\n완료! 파일, 설명, 분류 결과, 검색 인덱스 갱신 성공.")
    print("자동 분류 결과:", PROJECT_DIR / "Role02" / "metadata_classification_generated.csv")
    print("검색 인덱스:", PROJECT_DIR / "Role01" / "search_index")


if __name__ == "__main__":
    main()
