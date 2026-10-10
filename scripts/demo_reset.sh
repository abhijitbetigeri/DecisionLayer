#!/usr/bin/env bash
# Reset only an explicitly selected demo directory, then run on QA/demo port 8018.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PROOFPATH_DATA_DIR:?Set PROOFPATH_DATA_DIR to the dedicated demo data directory}"
uv run python - <<'PY'
import os, shutil
from pathlib import Path
raw=Path(os.environ['PROOFPATH_DATA_DIR']).expanduser()
if raw.is_symlink(): raise SystemExit('Refusing to reset a symlink')
p=raw.resolve()
repo=Path.cwd().resolve()
if p in repo.parents or p in (Path('/'),Path.home(),repo) or len(p.parts)<3 or p.name in ('runs','data','sv') or (repo/'runs')==p or (repo/'runs') in p.parents:
    raise SystemExit('Refusing to reset a protected or ambiguous directory')
if p.exists() and not (p/'proofpath.db').is_file():
    raise SystemExit('Refusing to reset directory without proofpath.db')
if p.exists(): shutil.rmtree(p)
p.mkdir(parents=True,exist_ok=True)
print('Reset dedicated Evaluation Workspace data directory:',p)
PY
exec uv run python -m uvicorn sv.proofpath.app:app --host 127.0.0.1 --port 8018
