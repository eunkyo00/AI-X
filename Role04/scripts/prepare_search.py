"""Validate the live Role01 engine used by automatic file registration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'Role01'


def main():
    required = ['Role01/search_engine.py', 'Role01/refresh_search.py',
                'Role01/file_reload_append_only.py', 'Role01/extract_content.py',
                'Role01/automation_code/file_watcher.py', 'update_pipeline_integrated.py',
                'Role02/description_generator.py', 'Role02/classify_metadata.py',
                'Role02/project_classifier_artifacts_v3/project_classifier_v3.joblib',
                'Role02/role_classifier_artifacts/role_classifier.joblib']
    missing = [name for name in required if not (ROOT/name).is_file()]
    if missing:
        raise SystemExit('최신 저장소 전체가 필요합니다. 누락된 파일: '+', '.join(missing))
    print(f'검색·자동 갱신 엔진 준비 완료: {TARGET}')
    print('등록 파일과 감시 폴더는 GUI 서버가 켜져 있는 동안 자동 갱신됩니다.')


if __name__ == '__main__':
    main()
