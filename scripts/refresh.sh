#!/bin/bash
# Full refresh: download anything new, rebuild, validate. Pass extra args to fetch.py.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=".venv/bin/python"
[ -x "$PY" ] || { echo "Run scripts/setup.sh first."; exit 1; }
mkdir -p logs
STAMP=$(date +%Y-%m-%d_%H%M)
{
  "$PY" scripts/fetch.py "$@"
  "$PY" scripts/build.py
  "$PY" scripts/validate.py
} 2>&1 | tee "logs/refresh_$STAMP.log"
