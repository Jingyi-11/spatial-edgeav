#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Installing common RK3567 camera/audio/video tools.

Board-vendor SDKs may provide Rockchip-specific packages such as:
  - mpp
  - rga
  - gstreamer-rockchip
  - rkmedia
  - rknn runtime

If apt cannot find those packages, use your board vendor image/SDK.
EOF

sudo apt update
sudo apt install -y \
  build-essential \
  v4l-utils \
  media-ctl \
  ffmpeg \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  alsa-utils
