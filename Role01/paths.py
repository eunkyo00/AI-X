"""Portable paths relative to Role01, independent of the working directory."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def resolve_path(value, base=BASE_DIR):
    value = str(value).replace('\\', '/')
    # Historical CSVs may contain an absolute path from another computer.
    marker = 'dataset/files/'
    if marker in value:
        return Path(base) / marker / value.split(marker, 1)[1]
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(base) / path


def path_key(value, base=BASE_DIR):
    return str(resolve_path(value, base).resolve())
