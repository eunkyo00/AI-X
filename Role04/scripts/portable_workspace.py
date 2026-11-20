"""Use copies when Windows cannot create staging symlinks."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil


def link_or_copy(source, destination):
    source, destination = Path(source), Path(destination)
    try:
        destination.symlink_to(source, target_is_directory=source.is_dir())
    except OSError:
        if os.name != 'nt':
            raise
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)


@contextmanager
def portable_team_links():
    """The team updater runs in its own subprocess; patch only for that call."""
    if os.name != 'nt':
        yield
        return
    original = Path.symlink_to
    def create(path, target, target_is_directory=False):
        try:
            return original(path, target, target_is_directory=target_is_directory)
        except OSError:
            if Path(target).is_dir():
                shutil.copytree(target, path)
            else:
                shutil.copy2(target, path)
    Path.symlink_to = create
    try:
        yield
    finally:
        Path.symlink_to = original
