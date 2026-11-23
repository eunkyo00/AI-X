"""Role01 can call these functions without loading a model or rebuilding DB."""
import json
from pathlib import Path
from file_db import get_file, get_relations

DB = Path(__file__).resolve().parent / 'output/files.sqlite3'
file = get_file(DB, 'F129')
print(json.dumps({key: file[key] for key in ['file_id', 'filename', 'project', 'role', 'description', 'extraction_status']}, ensure_ascii=False, indent=2))
print(json.dumps(get_relations(DB, 'F129'), ensure_ascii=False, indent=2))
