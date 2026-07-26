#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-rk3576}"
DEVICE="${2:-/dev/video73}"
PROFILE="${3:-indoor}"

case "${PROFILE}" in
  indoor)
    CTRLS="brightness=170,contrast=140,saturation=135,gain=80,backlight_compensation=1,exposure_dynamic_framerate=0"
    ;;
  bright)
    CTRLS="brightness=145,contrast=130,saturation=130,gain=30,backlight_compensation=0,exposure_dynamic_framerate=0"
    ;;
  default)
    CTRLS="brightness=128,contrast=128,saturation=128,gain=0,backlight_compensation=0,exposure_dynamic_framerate=1,auto_exposure=3"
    ;;
  manual-lowlight)
    CTRLS="auto_exposure=1,exposure_time_absolute=500,brightness=170,contrast=140,saturation=135,gain=100,backlight_compensation=1,exposure_dynamic_framerate=0"
    ;;
  *)
    echo "Unknown profile: ${PROFILE}" >&2
    echo "Profiles: indoor, bright, default, manual-lowlight" >&2
    exit 2
    ;;
esac

echo "Applying ${PROFILE} camera profile on ${HOST}:${DEVICE}"
ssh -o BatchMode=yes -o ConnectTimeout=8 "${HOST}" \
  "v4l2-ctl --device='${DEVICE}' --set-ctrl='${CTRLS}' && \
   v4l2-ctl --device='${DEVICE}' --get-ctrl=brightness,contrast,saturation,gain,backlight_compensation,exposure_dynamic_framerate,auto_exposure,exposure_time_absolute"
