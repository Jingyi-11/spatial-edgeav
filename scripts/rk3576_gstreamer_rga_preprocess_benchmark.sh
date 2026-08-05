#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
DEVICE="${DEVICE:-/dev/video73}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
FRAMES="${FRAMES:-180}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
LOCAL_OUT="${LOCAL_OUT:-runs/rk3576_media_accel}"

mkdir -p "${LOCAL_OUT}"

ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "DEVICE='${DEVICE}' WIDTH='${WIDTH}' HEIGHT='${HEIGHT}' FPS='${FPS}' FRAMES='${FRAMES}' REMOTE_ROOT='${REMOTE_ROOT}' bash -s" <<'REMOTE'
set -euo pipefail

OUT_DIR="${REMOTE_ROOT}/runs/media_accel"
REPORT="${OUT_DIR}/gstreamer_rga_preprocess_report.json"
mkdir -p "${OUT_DIR}"

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'
}

run_pipeline() {
  local name="$1"
  shift
  local log="${OUT_DIR}/${name}.log"
  local status="ok"
  local start_ms end_ms elapsed_ms fps
  start_ms="$(date +%s%3N)"
  if "$@" >"${log}" 2>&1; then
    status="ok"
  else
    status="failed"
  fi
  end_ms="$(date +%s%3N)"
  elapsed_ms="$((end_ms - start_ms))"
  fps="$(python3 - <<PY
frames = float("${FRAMES}")
elapsed_ms = float("${elapsed_ms}")
print(round(frames / (elapsed_ms / 1000.0), 3) if elapsed_ms > 0 else 0.0)
PY
)"
  printf '{"name":"%s","status":"%s","frames":%s,"elapsed_ms":%s,"fps":%s,"log":"%s"}' \
    "${name}" "${status}" "${FRAMES}" "${elapsed_ms}" "${fps}" "${log}"
}

GST_VERSION="$(gst-launch-1.0 --version 2>/dev/null | head -1 || true)"
GST_INSPECT="$(command -v gst-inspect-1.0 || true)"
GST_LAUNCH="$(command -v gst-launch-1.0 || true)"
RGA_DEVICE="missing"
if [ -e /dev/rga ]; then
  RGA_DEVICE="present"
fi
RGA_VERSION="$(pkg-config --modversion librga 2>/dev/null || true)"
GST_APP_VERSION="$(pkg-config --modversion gstreamer-app-1.0 2>/dev/null || true)"

HW_ELEMENTS=""
if [ -n "${GST_INSPECT}" ]; then
  HW_ELEMENTS="$(gst-inspect-1.0 2>/dev/null | grep -Ei 'rga|mpp|rockchip|rkx|v4l2.*convert|jpegdec' | head -80 || true)"
fi

PIPELINES="[]"
if [ -n "${GST_LAUNCH}" ]; then
  software_json="$(run_pipeline software_jpegdec_rgb640 \
    gst-launch-1.0 -q \
      v4l2src device="${DEVICE}" num-buffers="${FRAMES}" \
      ! "image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
      ! jpegparse \
      ! jpegdec \
      ! videoconvert \
      ! videoscale \
      ! video/x-raw,format=RGB,width=640,height=640 \
      ! fakesink sync=false)"

  hw_json=""
  if gst-inspect-1.0 mppjpegdec >/dev/null 2>&1; then
    hw_json="$(run_pipeline rockchip_mppjpegdec_rgb640 \
      gst-launch-1.0 -q \
        v4l2src device="${DEVICE}" num-buffers="${FRAMES}" \
        ! "image/jpeg,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
        ! jpegparse \
        ! mppjpegdec \
        ! videoconvert \
        ! videoscale \
        ! video/x-raw,format=RGB,width=640,height=640 \
        ! fakesink sync=false)"
  fi

  if [ -n "${hw_json}" ]; then
    PIPELINES="[${software_json},${hw_json}]"
  else
    PIPELINES="[${software_json}]"
  fi
fi

python3 - <<PY >"${REPORT}"
import json
payload = {
    "status": "ok",
    "device": "${DEVICE}",
    "camera": {"width": int("${WIDTH}"), "height": int("${HEIGHT}"), "fps": int("${FPS}"), "frames": int("${FRAMES}")},
    "gstreamer": {
        "gst_launch": bool("${GST_LAUNCH}"),
        "gst_inspect": bool("${GST_INSPECT}"),
        "version": ${GST_VERSION@Q},
        "app_version": ${GST_APP_VERSION@Q},
        "hardware_element_candidates": ${HW_ELEMENTS@Q}.splitlines(),
    },
    "rga": {
        "device": "${RGA_DEVICE}",
        "librga_version": ${RGA_VERSION@Q},
        "usable_from_current_runtime": False,
        "note": "Current C/C++ runtime still uses CPU libjpeg decode/resize; this report gates a future RGA/GStreamer hot-path integration."
    },
    "pipelines": ${PIPELINES},
}
print(json.dumps(payload, indent=2, ensure_ascii=False))
PY

cat "${REPORT}"
REMOTE

scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_ROOT}/runs/media_accel/gstreamer_rga_preprocess_report.json" \
  "${LOCAL_OUT}/"

echo "Wrote ${LOCAL_OUT}/gstreamer_rga_preprocess_report.json"
