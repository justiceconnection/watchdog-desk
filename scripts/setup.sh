#!/bin/bash
# One-time setup: creates a Python virtual environment in .venv and installs DuckDB.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3 not found. Install it with:  xcode-select --install   (or: brew install python)"
  exit 1
fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "Python 3.9+ is required; found $("$PY" --version)."; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
.venv/bin/python -c "import duckdb; print('DuckDB', duckdb.__version__, 'installed')"
mkdir -p data logs
echo
echo "Setup complete. Before running scripts in a new Terminal window:"
echo "  cd \"$(pwd)\" && source .venv/bin/activate"
