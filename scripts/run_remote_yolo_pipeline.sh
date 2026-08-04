#!/usr/bin/env bash
set -euo pipefail

RK_HOST="${1:-rk3576}"
WSL_HOST="${2:-wslbox}"
DEVICE="${3:-/dev/video73}"
WIDTH="${4:-1280}"
HEIGHT="${5:-720}"
FPS="${6:-30}"
RUN_ROOT="${7:-runs/edgeav_remote_yolo}"
WIN_HOST="${WIN_HOST:-winbox}"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${RUN_ROOT}/${STAMP}"
RK_REMOTE_DIR="/tmp/edgeav_remote_yolo/${STAMP}"
WIN_RUN_DIR="C:/Users/HP/edgeav_data/edgeav_remote_yolo/${STAMP}"
WSL_RUN_DIR="/mnt/c/Users/HP/edgeav_data/edgeav_remote_yolo/${STAMP}"

LOCAL_INPUT="${RUN_DIR}/input.jpg"
LOCAL_ANNOTATED="${RUN_DIR}/annotated.jpg"
LOCAL_DETECTIONS="${RUN_DIR}/detections.json"
LOCAL_INFERENCE="${RUN_DIR}/inference.json"
LOCAL_LATENCY="${RUN_DIR}/latency.json"
LOCAL_SUMMARY="${RUN_DIR}/summary.txt"

RK_IMAGE="${RK_REMOTE_DIR}/input.jpg"
WSL_IMAGE="${WSL_RUN_DIR}/input.jpg"
WSL_HELPER="${WSL_RUN_DIR}/wsl_yolo_infer.py"
WSL_ANNOTATED="${WSL_RUN_DIR}/annotated.jpg"
WSL_DETECTIONS="${WSL_RUN_DIR}/detections.json"
WSL_INFERENCE="${WSL_RUN_DIR}/inference.json"
HELPER_SCRIPT="scripts/wsl_yolo_infer.py"

MODEL_MODE=""

mkdir -p "${RUN_DIR}"

now_ms() {
  python3 -c 'import time; print(int(time.time() * 1000))'
}

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

require_ssh() {
  local label="$1"
  local host="$2"
  echo "Checking ${label} SSH (${host})..."
  if ! retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${host}" 'true'; then
    echo "ERROR: cannot reach ${label} via SSH host '${host}'." >&2
    echo "Check Tailscale, power/sleep state, sshd, and SSH config, then rerun this script." >&2
    exit 20
  fi
}

choose_model_mode() {
  echo "Checking WSL model host SSH (${WSL_HOST})..."
  if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'true'; then
    MODEL_MODE="direct_wsl"
    echo "model_mode=${MODEL_MODE}"
    return 0
  fi

  echo "Direct WSL SSH is unavailable; trying Windows bridge (${WIN_HOST} -> wsl.exe)..." >&2
  if retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" 'hostname'; then
    MODEL_MODE="windows_bridge"
    echo "model_mode=${MODEL_MODE}"
    return 0
  fi

  echo "ERROR: neither ${WSL_HOST} nor ${WIN_HOST} is reachable for model inference." >&2
  exit 20
}

run_step() {
  local name="$1"
  shift
  echo "== ${name} =="
  local start_ms end_ms elapsed_ms
  start_ms="$(now_ms)"
  "$@"
  end_ms="$(now_ms)"
  elapsed_ms="$((end_ms - start_ms))"
  printf '%s_ms=%s\n' "${name}" "${elapsed_ms}" >> "${RUN_DIR}/timings.env"
}

ensure_wsl_deps_direct() {
  retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'set -e
if ! python3 -m pip --version >/dev/null 2>&1; then
  mkdir -p "$HOME/edgeav_setup"
  cd "$HOME/edgeav_setup"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSLO https://bootstrap.pypa.io/get-pip.py
  else
    wget -q https://bootstrap.pypa.io/get-pip.py
  fi
  python3 get-pip.py --user
fi
python3 - <<'"'"'PY'"'"' >/dev/null 2>&1 || python3 -m pip install --user --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cpu
import torch, torchvision
PY
python3 - <<'"'"'PY'"'"' >/dev/null 2>&1 || python3 -m pip install --user --upgrade ultralytics opencv-python-headless
import ultralytics, cv2
PY
'
}

ensure_wsl_deps_bridge() {
  retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
    "cmd /c wsl -d Ubuntu-22.04 --exec /bin/bash -lc \"set -e; \
     python3 -m pip --version >/dev/null 2>&1; \
     python3 -c 'import torch, torchvision, ultralytics, cv2' >/dev/null 2>&1\""
}

prepare_model_workspace() {
  if [[ "${MODEL_MODE}" == "direct_wsl" ]]; then
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" \
      "mkdir -p '${WSL_RUN_DIR}'"
    retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
      "${LOCAL_INPUT}" "${HELPER_SCRIPT}" "${WSL_HOST}:${WSL_RUN_DIR}/"
  else
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
      "if not exist \"${WIN_RUN_DIR}\" mkdir \"${WIN_RUN_DIR}\""
    retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
      "${LOCAL_INPUT}" "${HELPER_SCRIPT}" "${WIN_HOST}:${WIN_RUN_DIR}/"
  fi
}

run_model_inference() {
  local command="set -e; export PATH=\"\$HOME/.local/bin:\$PATH\"; export YOLO_CONFIG_DIR=/mnt/c/Users/HP/edgeav_data/ultralytics_config; mkdir -p \"\$YOLO_CONFIG_DIR\"; python3 '${WSL_HELPER}' '${WSL_IMAGE}' '${WSL_ANNOTATED}' '${WSL_DETECTIONS}' '${WSL_INFERENCE}'"
  if [[ "${MODEL_MODE}" == "direct_wsl" ]]; then
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" "${command}"
  else
    retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${WIN_HOST}" \
      "cmd /c wsl -d Ubuntu-22.04 --exec /bin/bash -lc \"${command}\""
  fi
}

pull_model_results() {
  if [[ "${MODEL_MODE}" == "direct_wsl" ]]; then
    retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
      "${WSL_HOST}:${WSL_ANNOTATED}" \
      "${WSL_HOST}:${WSL_DETECTIONS}" \
      "${WSL_HOST}:${WSL_INFERENCE}" \
      "${RUN_DIR}/"
  else
    retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
      "${WIN_HOST}:${WIN_RUN_DIR}/annotated.jpg" \
      "${WIN_HOST}:${WIN_RUN_DIR}/detections.json" \
      "${WIN_HOST}:${WIN_RUN_DIR}/inference.json" \
      "${RUN_DIR}/"
  fi
}

echo "Spatial EdgeAV remote YOLO pipeline"
echo "run_dir=${RUN_DIR}"
echo "rk_host=${RK_HOST} wsl_host=${WSL_HOST} win_host=${WIN_HOST} device=${DEVICE} size=${WIDTH}x${HEIGHT}@${FPS}"

require_ssh "RK3576 board" "${RK_HOST}"
choose_model_mode

TOTAL_START_MS="$(now_ms)"

run_step capture_rk3576 retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${RK_HOST}" \
  "set -e; \
   mkdir -p '${RK_REMOTE_DIR}'; \
   gst-launch-1.0 -q -e \
     v4l2src device='${DEVICE}' num-buffers=1 \
     ! image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1 \
     ! filesink location='${RK_IMAGE}'; \
   ls -lh '${RK_IMAGE}'; \
   file '${RK_IMAGE}'"

run_step pull_frame_to_mac retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${RK_HOST}:${RK_IMAGE}" \
  "${LOCAL_INPUT}"

if [[ "${MODEL_MODE}" == "direct_wsl" ]]; then
  run_step prepare_wsl ensure_wsl_deps_direct
else
  run_step prepare_wsl_bridge ensure_wsl_deps_bridge
fi
run_step prepare_model_workspace prepare_model_workspace
run_step infer_wsl run_model_inference
run_step pull_results_to_mac pull_model_results

TOTAL_END_MS="$(now_ms)"
TOTAL_MS="$((TOTAL_END_MS - TOTAL_START_MS))"

python3 - "${RUN_DIR}/timings.env" "${LOCAL_INFERENCE}" "${LOCAL_DETECTIONS}" "${LOCAL_LATENCY}" "${TOTAL_MS}" "${MODEL_MODE}" <<'PY'
import json
import sys
from pathlib import Path

timings_path = Path(sys.argv[1])
inference_path = Path(sys.argv[2])
detections_path = Path(sys.argv[3])
latency_path = Path(sys.argv[4])
total_ms = int(sys.argv[5])
model_mode = sys.argv[6]

timings = {}
for line in timings_path.read_text(encoding="utf-8").splitlines():
    key, value = line.split("=", 1)
    timings[key] = int(value)

inference = json.loads(inference_path.read_text(encoding="utf-8"))
detections = json.loads(detections_path.read_text(encoding="utf-8"))

payload = {
    "total_ms": total_ms,
    "model_mode": model_mode,
    "steps_ms": timings,
    "model_ms": inference.get("ultralytics_ms", {}),
    "detections_count": len(detections.get("detections", [])),
}
latency_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

python3 - "${LOCAL_DETECTIONS}" "${LOCAL_LATENCY}" "${LOCAL_SUMMARY}" <<'PY'
import json
import sys
from pathlib import Path

detections = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
latency = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
classes = ", ".join(d["class_name"] for d in detections.get("detections", []))
lines = [
    "Spatial EdgeAV remote YOLO pipeline summary",
    f"model_mode={latency.get('model_mode')}",
    f"objects={len(detections.get('detections', []))}",
    f"total_ms={latency.get('total_ms')}",
    f"classes={classes}",
]
Path(sys.argv[3]).write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
PY

echo "Wrote:"
echo "  ${LOCAL_INPUT}"
echo "  ${LOCAL_ANNOTATED}"
echo "  ${LOCAL_DETECTIONS}"
echo "  ${LOCAL_INFERENCE}"
echo "  ${LOCAL_LATENCY}"
echo "  ${LOCAL_SUMMARY}"
