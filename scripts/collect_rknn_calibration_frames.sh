#!/usr/bin/env bash
set -euo pipefail

SOURCE_GLOB="${1:-runs/edgeav_remote_yolo/*/input.jpg}"
OUT_DIR="${2:-runs/model_exports/yolov8n/calib}"
MAX_IMAGES="${3:-100}"

mkdir -p "${OUT_DIR}/images"
: > "${OUT_DIR}/dataset.txt"

count=0
for image in ${SOURCE_GLOB}; do
  if [[ ! -f "${image}" ]]; then
    continue
  fi
  name="$(printf 'calib_%04d.jpg' "${count}")"
  cp "${image}" "${OUT_DIR}/images/${name}"
  printf '%s\n' "${OUT_DIR}/images/${name}" >> "${OUT_DIR}/dataset.txt"
  count=$((count + 1))
  if (( count >= MAX_IMAGES )); then
    break
  fi
done

if (( count == 0 )); then
  echo "No calibration images matched: ${SOURCE_GLOB}" >&2
  exit 1
fi

echo "Wrote ${count} calibration image(s):"
echo "  ${OUT_DIR}/images/"
echo "  ${OUT_DIR}/dataset.txt"
