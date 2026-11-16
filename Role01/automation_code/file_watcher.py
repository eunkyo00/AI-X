"""Use one file watcher and integrated refresh queue for the GUI and CLI."""
from functools import partial
from pathlib import Path
import sys
import time

PROJECT_DIR = Path(__file__).resolve().parents[2]


def create_watcher(root=PROJECT_DIR):
    # Importing this module must not start threads or execute the pipeline.
    from auto_refresh import AutoRefresh
    from update_data import update
    watcher = AutoRefresh(root, updater=partial(update, integrated=True))
    watcher.request('서버 시작 · 설명·분류·검색 인덱스 확인')
    return watcher


def main():
    sys.path.insert(0, str(PROJECT_DIR))
    watcher = create_watcher().start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.close()


if __name__ == '__main__':
    main()
