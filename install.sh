#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
if [[ -x .venv/bin/python || -x faster-whisper/.venv/bin/python ]]; then
  if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=faster-whisper/.venv/bin/python; fi
  if command -v uv >/dev/null && ! "$PY" -m pip --version >/dev/null 2>&1; then
    uv pip install --python "$PY" -r requirements.txt
  else
    "$PY" -m pip install -r requirements.txt
  fi
  "$PY" bin/install_translation.py
  "$PY" bin/install_translation.py --pair es_en
  "$PY" bin/install_streaming.py
  echo 'Backend preparado. Abre ./app.sh'
  exit 0
fi
command -v python3.12 >/dev/null || { echo 'Se necesita Python 3.12 para esta instalación.' >&2; exit 1; }
for command_name in parec pactl; do
  command -v "$command_name" >/dev/null || { echo 'Falta pulseaudio-utils (parec y pactl), compatible con PipeWire.' >&2; exit 1; }
done
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python bin/install_translation.py
.venv/bin/python bin/install_translation.py --pair es_en
.venv/bin/python bin/install_streaming.py
echo 'Preparado. Abre ./app.sh y desmarca Solo modelos descargados para descargar Whisper la primera vez.'
