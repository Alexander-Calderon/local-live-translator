#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONUTF8=1
if [[ -x "$DIR/.venv/bin/python" ]]; then PY="$DIR/.venv/bin/python"
elif [[ -x "$DIR/faster-whisper/.venv/bin/python" ]]; then PY="$DIR/faster-whisper/.venv/bin/python"
else PY=python3; fi
exec "$PY" "$DIR/bin/app.py" "$@"
