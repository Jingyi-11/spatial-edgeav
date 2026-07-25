#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
RK3567 AI inference deployment checklist
========================================

1. Confirm NPU runtime from board vendor:
   ls /usr/lib | grep -Ei 'rknn|rknpu'
   ls /usr/bin | grep -Ei 'rknn|rknpu'

2. Convert model on PC:
   ONNX/PyTorch -> RKNN using rknn-toolkit2

3. Run on board:
   Camera NV12 -> resize/letterbox with RGA or CPU -> RKNN inference -> draw boxes -> encode/stream

4. Useful repos:
   https://github.com/airockchip/rknn-toolkit2
   https://github.com/airockchip/rknn_model_zoo
   https://github.com/rockchip-linux/mpp
   https://github.com/bluenviron/mediamtx

This project currently provides the capture/encode/stream skeleton.
The next coding stage is adding an RKNN inference module between capture and encode.
EOF
