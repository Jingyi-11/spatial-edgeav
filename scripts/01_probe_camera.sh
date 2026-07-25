#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-/dev/video0}"

echo "== v4l2 device list =="
v4l2-ctl --list-devices

echo
echo "== formats for ${DEVICE} =="
v4l2-ctl -d "${DEVICE}" --list-formats-ext

echo
echo "== controls for ${DEVICE} =="
v4l2-ctl -d "${DEVICE}" --list-ctrls
