import time
import subprocess
import sys
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 1. 기본 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent
WATCH_DIR = BASE_DIR / "dataset" / "files"

# 2. 기존 코드 실행
def run_script(filename, *args):
    print(f"\n실행 중: {filename}")

    subprocess.run(
        [sys.executable, str(BASE_DIR / filename), *args],
        cwd=BASE_DIR,
        check=True
    )

# 3. 파일 등록 및 텍스트 추출
def update_files():
    # 1. 메타데이터 갱신 (백업 생성 X)
    run_script("file_reload_code.py", "--no-backup")

    # 2. 텍스트 추출 (캐싱 적용)
    run_script("extract_content.py")

    print("파일 자동 갱신 완료!")

# 4. 파일 변경 감지
class FileHandler(FileSystemEventHandler):

    def __init__(self):
        self.last_change = 0

    def on_any_event(self, event):
        if event.is_directory:
            return

        if event.event_type not in ("created", "modified", "moved", "deleted"):
            return

        self.last_change = time.monotonic()
        print("파일 변경 감지:", event.src_path)

# 5. 감시 시작
WATCH_DIR.mkdir(parents=True, exist_ok=True)

handler = FileHandler()
observer = Observer()
observer.schedule(handler, str(WATCH_DIR), recursive=True)
observer.start()

print("파일 자동 감시 시작!")
print("감시 폴더:", WATCH_DIR)

try:
    # 프로그램 실행 전에 추가된 파일도 확인
    update_files()

    while True:
        time.sleep(1)

        # 마지막 변경 이후 3초 동안 새 이벤트가 없으면 실행
        if handler.last_change:
            if time.monotonic() - handler.last_change >= 3:
                handler.last_change = 0
                update_files()

except KeyboardInterrupt:
    print("\n파일 감시 종료")

finally:
    observer.stop()
    observer.join()