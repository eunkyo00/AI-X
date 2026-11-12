
import time
import subprocess
import sys
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 1. 기본 경로 설정
PROJECT_DIR = Path(__file__).resolve().parents[2]
WATCH_DIR = PROJECT_DIR / "Role01" / "dataset" / "files"

# 2. 통합 파이프라인 실행
def update_files():
    print("\n파일 갱신 시작!", flush=True)

    result = subprocess.run(
        [sys.executable, str(PROJECT_DIR / "update_pipeline.py")],
        cwd=PROJECT_DIR
    )

    if result.returncode == 0:
        print("\n파일 자동 갱신 완료!")
    else:
        print("\n파일 갱신 실패! 종료 코드:", result.returncode)

# 3. 파일 변경 감지
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

# 4. 감시 시작
WATCH_DIR.mkdir(parents=True, exist_ok=True)

handler = FileHandler()
observer = Observer()
observer.schedule(handler, str(WATCH_DIR), recursive=True)
observer.start()

print("파일 자동 감시 시작!")
print("감시 폴더:", WATCH_DIR)

try:
    # 시작할 때 기존 파일도 확인
    update_files()

    while True:
        time.sleep(1)

        # 마지막 변경 후 3초 동안 이벤트가 없으면 갱신
        if handler.last_change:
            if time.monotonic() - handler.last_change >= 3:
                handler.last_change = 0
                update_files()

except KeyboardInterrupt:
    print("\n파일 감시 종료")

finally:
    observer.stop()
    observer.join()
