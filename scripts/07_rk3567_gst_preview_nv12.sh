#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-30}"
FORMAT="${FORMAT:-NV12}"

gst-launch-1.0 -v \
  v4l2src device="${DEVICE}" io-mode=mmap \
  ! "video/x-raw,format=${FORMAT},width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
  ! videoconvert \
  ! autovideosink sync=false
