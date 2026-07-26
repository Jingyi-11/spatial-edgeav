#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"

echo "== RK3567 kernel =="
uname -a

echo
echo "== Rockchip camera/media nodes =="
ls -l /dev/video* /dev/media* /dev/v4l-subdev* 2>/dev/null || true

echo
echo "== v4l2 devices =="
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-devices || true
else
  echo "v4l2-ctl not found. Install v4l-utils."
fi

echo
echo "== media graph =="
if command -v media-ctl >/dev/null 2>&1; then
  for media in /dev/media*; do
    [ -e "${media}" ] || continue
    echo
    echo "-- ${media} --"
    media-ctl -d "${media}" -p || true
  done
else
  echo "media-ctl not found. Install media-ctl."
fi

echo
echo "== formats for ${DEVICE} =="
if [ -e "${DEVICE}" ] && command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl -d "${DEVICE}" --all || true
  v4l2-ctl -d "${DEVICE}" --list-formats-ext || true
  v4l2-ctl -d "${DEVICE}" --list-ctrls || true
else
  echo "${DEVICE} not found."
fi

echo
echo "== Rockchip/GStreamer encoder plugins =="
if command -v gst-inspect-1.0 >/dev/null 2>&1; then
  for plugin in mpph264enc mpph265enc v4l2h264enc v4l2h265enc x264enc; do
    if gst-inspect-1.0 "${plugin}" >/dev/null 2>&1; then
      echo "found: ${plugin}"
    else
      echo "missing: ${plugin}"
    fi
  done
else
  echo "gst-inspect-1.0 not found."
fi

echo
echo "Tip: for MIPI CSI, the correct capture node is often the rkisp/rkcif video node, not always /dev/video0."
