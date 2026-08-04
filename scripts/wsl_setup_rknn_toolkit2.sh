#!/usr/bin/env bash
set -euo pipefail

WIN_HOST="${WIN_HOST:-winbox}"
WSL_HOST="${WSL_HOST:-wslbox}"
RKNN_VERSION="${1:-2.3.2}"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"

retry_command() {
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if (( attempt >= SSH_RETRIES )); then
      return 1
    fi
    echo "Command failed; retrying in ${SSH_RETRY_DELAY_SEC}s (${attempt}/${SSH_RETRIES})..." >&2
    sleep "${SSH_RETRY_DELAY_SEC}"
    attempt=$((attempt + 1))
  done
}

run_wsl() {
  local command="$1"
  if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'true'; then
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" "${command}"
  else
    echo "Direct WSL SSH unavailable; using ${WIN_HOST} -> wsl.exe bridge." >&2
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
      "cmd /c wsl -d Ubuntu-22.04 --exec /bin/bash -lc \"${command}\""
  fi
}

echo "Installing RKNN-Toolkit2 ${RKNN_VERSION} inside WSL..."
run_wsl "set -e; \
  python3 -m pip install --user --upgrade \
    'numpy<=1.26.4' \
    'protobuf>=4.21.6,<=4.25.4' \
    'onnx==1.16.1' \
    'onnxruntime>=1.10.0' \
    'scipy>=1.9.3' \
    'ruamel.yaml>=0.17.21' \
    'tqdm>=4.64.1' \
    'fast-histogram>=0.11'; \
  python3 -m pip install --user --upgrade --no-deps 'rknn-toolkit2==${RKNN_VERSION}'; \
  python3 - <<'PY'
import onnx
from rknn.api import RKNN
print('onnx', onnx.__version__)
print('rknn.api import OK')
PY"

echo "RKNN-Toolkit2 setup complete."
