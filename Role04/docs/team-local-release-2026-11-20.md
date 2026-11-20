# 팀원별 로컬 실행 배포 · 2026-11-20

공유 브랜치: `codex/gui-team-local-launch`. 최신 main `b2408a5`에서 GUI 변경만 반영했다. Role01·02·03의 최신 팀 소스는 그대로 유지한다. GUI 실행용 엔진은 검증된 `97b6d5f` 스냅샷을 별도 runtime 폴더에 준비하며 기본 파일은 202개다.

## 포함 범위

macOS·Windows 최초 설치 및 실행 파일, GUI/API, 파일 등록·관계·설명·분류·폴더 자동 갱신, 설치 문서와 회귀 테스트를 포함한다. Windows 링크 권한이 없으면 임시 데이터 복사 방식으로 처리한다. Windows 실기기 실행은 미검증이다.

개인 업로드, 감시 폴더 설정, 모델·인덱스 캐시, SQLite 실행 DB와 로그는 runtime에 보관하며 Git에서 제외한다. 기존 로컬 개발 폴더는 수정하거나 정리하지 않는다.

## 검증

- Python GUI·API·통합·Windows 복사 대안 테스트 21개 통과.
- JavaScript 검색·어댑터 테스트 23개 통과.
- macOS 설치/실행 셸 구문 및 실행 권한, git diff --check 확인.
- 새 실행 폴더에서 Git 스냅샷 기본 자료 202개 준비 확인.

처음 사용 방법은 [GUI 실행 안내](../GUI%20실행/README.md)를 따른다. Qwen 신규 설명 생성은 로컬 Ollama의 qwen3.5:4b 실행이 필요한 선택 기능이다.
