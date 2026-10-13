#!/usr/bin/env bash
# Lanzador. Pone las librerias CUDA del venv en el PATH de bibliotecas
# (ctranslate2 necesita cuDNN 9 y cuBLAS, y aqui van dentro del entorno,
# no instaladas a nivel de sistema).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == '--choose' ]]; then
  shift
  cat >&2 <<'MENU'
Elige un perfil de Whisper:
  1) base en vivo   : recomendado para lectura rápida
  2) small en vivo  : tamaño intermedio
  3) medium por segmentos: más precisión en clips; texto con mayor demora
  4) medium en vivo : experimental; puede acumular retraso en esta GPU
MENU
  read -r -p 'Opción [1]: ' selection || selection=1
  case "${selection:-1}" in
    1|base) set -- "$@" --live --model base ;;
    2|small) set -- "$@" --live --model small ;;
    3|medium) set -- --segment 8 "$@" --asr whisper --profile custom --model medium --mode phrase --view web ;;
    4) set -- "$@" --live --model medium ;;
    *) echo 'Opción inválida. Usa 1, 2, 3 o 4.' >&2; exit 2 ;;
  esac
fi
PY="$DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="$DIR/faster-whisper/.venv/bin/python"; fi
if [[ ! -x "$PY" ]]; then
  echo 'Falta el entorno Python. Consulta la instalación del README.' >&2
  exit 1
fi
SP="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"
export LD_LIBRARY_PATH="$SP/nvidia/cudnn/lib:$SP/nvidia/cublas/lib:$SP/nvidia/cuda_nvrtc/lib:${LD_LIBRARY_PATH:-}"
exec "$PY" "$DIR/bin/listen.py" "$@"
