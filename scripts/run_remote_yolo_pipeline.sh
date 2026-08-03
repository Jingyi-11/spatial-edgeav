#!/usr/bin/env bash
set -euo pipefail

RK_HOST="${1:-rk3576}"
WSL_HOST="${2:-wslbox}"
DEVICE="${3:-/dev/video73}"
WIDTH="${4:-1280}"
HEIGHT="${5:-720}"
FPS="${6:-30}"
RUN_ROOT="${7:-runs/edgeav_remote_yolo}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${RUN_ROOT}/${STAMP}"
RK_REMOTE_DIR="/tmp/edgeav_remote_yolo/${STAMP}"
WSL_RUN_DIR="/mnt/c/Users/HP/edgeav_data/edgeav_remote_yolo/${STAMP}"

LOCAL_INPUT="${RUN_DIR}/input.jpg"
LOCAL_ANNOTATED="${RUN_DIR}/annotated.jpg"
LOCAL_DETECTIONS="${RUN_DIR}/detections.json"
LOCAL_INFERENCE="${RUN_DIR}/inference.json"
LOCAL_LATENCY="${RUN_DIR}/latency.json"
LOCAL_SUMMARY="${RUN_DIR}/summary.txt"

RK_IMAGE="${RK_REMOTE_DIR}/input.jpg"
WSL_IMAGE="${WSL_RUN_DIR}/input.jpg"
WSL_ANNOTATED="${WSL_RUN_DIR}/annotated.jpg"
WSL_DETECTIONS="${WSL_RUN_DIR}/detections.json"
WSL_INFERENCE="${WSL_RUN_DIR}/inference.json"

mkdir -p "${RUN_DIR}"

now_ms() {
  python3 -c 'import time; print(int(time.time() * 1000))'
}

check_ssh() {
  local label="$1"
  local host="$2"
  echo "Checking ${label} SSH (${host})..."
  if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "${host}" 'true'; then
    echo "ERROR: cannot reach ${label} via SSH host '${host}'." >&2
    echo "Check Tailscale, power/sleep state, sshd, and SSH config, then rerun this script." >&2
    exit 20
  fi
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

echo "Spatial EdgeAV remote YOLO pipeline"
echo "run_dir=${RUN_DIR}"
echo "rk_host=${RK_HOST} wsl_host=${WSL_HOST} device=${DEVICE} size=${WIDTH}x${HEIGHT}@${FPS}"

check_ssh "RK3576 board" "${RK_HOST}"
check_ssh "WSL model host" "${WSL_HOST}"

TOTAL_START_MS="$(now_ms)"

run_step capture_rk3576 ssh -o BatchMode=yes -o ConnectTimeout=8 "${RK_HOST}" \
  "set -e; \
   mkdir -p '${RK_REMOTE_DIR}'; \
   gst-launch-1.0 -q -e \
     v4l2src device='${DEVICE}' num-buffers=1 \
     ! image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1 \
     ! filesink location='${RK_IMAGE}'; \
   ls -lh '${RK_IMAGE}'; \
   file '${RK_IMAGE}'"

run_step pull_frame_to_mac scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${RK_HOST}:${RK_IMAGE}" \
  "${LOCAL_INPUT}"

run_step prepare_wsl ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" 'set -e
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

run_step push_frame_to_wsl ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" \
  "mkdir -p '${WSL_RUN_DIR}'"
run_step copy_frame_to_wsl scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${LOCAL_INPUT}" \
  "${WSL_HOST}:${WSL_IMAGE}"

run_step infer_wsl ssh -o BatchMode=yes -o ConnectTimeout=8 "${WSL_HOST}" \
  "set -e; \
   export PATH=\"\$HOME/.local/bin:\$PATH\"; \
   export YOLO_CONFIG_DIR=/mnt/c/Users/HP/edgeav_data/ultralytics_config; \
   mkdir -p \"\$YOLO_CONFIG_DIR\" '${WSL_RUN_DIR}'; \
   python3 - '${WSL_IMAGE}' '${WSL_ANNOTATED}' '${WSL_DETECTIONS}' '${WSL_INFERENCE}' <<'PY'
import json
import sys
import time
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

image_path = Path(sys.argv[1])
annotated_path = Path(sys.argv[2])
detections_path = Path(sys.argv[3])
inference_path = Path(sys.argv[4])

start = time.perf_counter()
model = YOLO('yolov8n.pt')
load_done = time.perf_counter()
result = model(str(image_path), imgsz=640, device='cpu', verbose=False)[0]
infer_done = time.perf_counter()

annotated = result.plot()
cv2.imwrite(str(annotated_path), annotated)

names = result.names
boxes = result.boxes
detections = []
if boxes is not None:
    xyxy = boxes.xyxy.cpu().tolist()
    conf = boxes.conf.cpu().tolist()
    cls = boxes.cls.cpu().tolist()
    for idx, (box, score, class_id) in enumerate(zip(xyxy, conf, cls)):
        x1, y1, x2, y2 = box
        detections.append({
            'id': idx,
            'class_id': int(class_id),
            'class_name': names[int(class_id)],
            'confidence': round(float(score), 4),
            'bbox_xyxy': [round(float(v), 2) for v in [x1, y1, x2, y2]],
            'bbox_xywh': [
                round(float(x1), 2),
                round(float(y1), 2),
                round(float(x2 - x1), 2),
                round(float(y2 - y1), 2),
            ],
        })

image = cv2.imread(str(image_path))
height, width = image.shape[:2] if image is not None else (None, None)
payload = {
    'source': str(image_path),
    'image': {'width': width, 'height': height},
    'model': 'yolov8n.pt',
    'device': 'cpu',
    'detections': detections,
}
detections_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

speed = getattr(result, 'speed', {}) or {}
inference = {
    'python_ms': {
        'model_load': round((load_done - start) * 1000, 3),
        'predict_total': round((infer_done - load_done) * 1000, 3),
    },
    'ultralytics_ms': {
        'preprocess': round(float(speed.get('preprocess', 0.0)), 3),
        'inference': round(float(speed.get('inference', 0.0)), 3),
        'postprocess': round(float(speed.get('postprocess', 0.0)), 3),
    },
    'environment': {
        'torch': torch.__version__,
        'cuda_available': torch.cuda.is_available(),
    },
}
inference_path.write_text(json.dumps(inference, indent=2), encoding='utf-8')
print(json.dumps({'detections': len(detections), **inference}, indent=2))
PY"

run_step pull_results_to_mac scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${WSL_HOST}:${WSL_ANNOTATED}" \
  "${WSL_HOST}:${WSL_DETECTIONS}" \
  "${WSL_HOST}:${WSL_INFERENCE}" \
  "${RUN_DIR}/"

TOTAL_END_MS="$(now_ms)"
TOTAL_MS="$((TOTAL_END_MS - TOTAL_START_MS))"

python3 - "${RUN_DIR}/timings.env" "${LOCAL_INFERENCE}" "${LOCAL_DETECTIONS}" "${LOCAL_LATENCY}" "${TOTAL_MS}" <<'PY'
import json
import sys
from pathlib import Path

timings_path = Path(sys.argv[1])
inference_path = Path(sys.argv[2])
detections_path = Path(sys.argv[3])
latency_path = Path(sys.argv[4])
total_ms = int(sys.argv[5])

timings = {}
for line in timings_path.read_text(encoding='utf-8').splitlines():
    key, value = line.split('=', 1)
    timings[key] = int(value)

inference = json.loads(inference_path.read_text(encoding='utf-8'))
detections = json.loads(detections_path.read_text(encoding='utf-8'))

payload = {
    'total_ms': total_ms,
    'steps_ms': timings,
    'model_ms': inference.get('ultralytics_ms', {}),
    'detections_count': len(detections.get('detections', [])),
}
latency_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
PY

python3 - "${LOCAL_DETECTIONS}" "${LOCAL_LATENCY}" "${LOCAL_SUMMARY}" <<'PY'
import json
import sys
from pathlib import Path

detections = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
latency = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
lines = [
    'Spatial EdgeAV remote YOLO pipeline summary',
    f"objects={len(detections.get('detections', []))}",
    f"total_ms={latency.get('total_ms')}",
    'classes=' + ', '.join(d['class_name'] for d in detections.get('detections', [])),
]
Path(sys.argv[3]).write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines))
PY

echo "Wrote:"
echo "  ${LOCAL_INPUT}"
echo "  ${LOCAL_ANNOTATED}"
echo "  ${LOCAL_DETECTIONS}"
echo "  ${LOCAL_LATENCY}"
echo "  ${LOCAL_SUMMARY}"
