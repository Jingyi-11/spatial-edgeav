#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"
WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-480}"
FPS="${FPS:-30}"

gst-launch-1.0 -v \
  v4l2src device="${DEVICE}" \
  ! "video/x-raw,width=${WIDTH},height=${HEIGHT},framerate=${FPS}/1" \
  ! videoconvert \
  ! autovideosink sync=false
