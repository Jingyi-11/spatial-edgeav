#!/usr/bin/env bash
set -euo pipefail

BOARD_HOST="${BOARD_HOST:-rk3576}"
SERVICE_NAME="${SERVICE_NAME:-spatial-edgeav-rknn.service}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/kickpi/spatial-edgeav}"
REMOTE_RUN_DIR="${REMOTE_ROOT}/runs/service"
LOCAL_ROOT="${LOCAL_ROOT:-runs/rk3576_service_snapshots}"
JOURNAL_LINES="${JOURNAL_LINES:-200}"
SSH_RETRIES="${SSH_RETRIES:-3}"
SSH_RETRY_DELAY_SEC="${SSH_RETRY_DELAY_SEC:-3}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${LOCAL_ROOT}/${STAMP}"

retry_command() {
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if (( attempt >= SSH_RETRIES )); then
      return 1
    fi
    echo "Command failed; retrying in ${SSH_RETRY_DELAY_SEC}s (${attempt}/${SSH_RETRIES})..." >&2
    sleep "${SSH_RETRY_DELAY_SEC}"
    attempt=$((attempt + 1))
  done
}

mkdir -p "${OUT_DIR}"

echo "Collecting ${SERVICE_NAME} snapshot from ${BOARD_HOST}..."

retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "systemctl is-active '${SERVICE_NAME}'" \
  > "${OUT_DIR}/is_active.txt"

retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "systemctl show '${SERVICE_NAME}' --no-pager \
    --property=Id,LoadState,ActiveState,SubState,UnitFileState,MainPID,NRestarts,ExecMainStartTimestamp,ExecMainStatus,MemoryCurrent,CPUUsageNSec" \
  > "${OUT_DIR}/systemctl_show.env"

retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "systemctl status '${SERVICE_NAME}' --no-pager" \
  > "${OUT_DIR}/systemctl_status.txt" || true

retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "journalctl -q -u '${SERVICE_NAME}' -n '${JOURNAL_LINES}' --no-pager" \
  > "${OUT_DIR}/journal_tail.txt" || true

retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "cat '${REMOTE_RUN_DIR}/heartbeat.json'" \
  > "${OUT_DIR}/heartbeat.json"

retry_command ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_HOST}" \
  "python3 - <<'PY'
import json
import os
import platform
import subprocess
from pathlib import Path

service = os.environ.get('SERVICE_NAME', 'spatial-edgeav-rknn.service')
remote_run_dir = Path(os.environ.get('REMOTE_RUN_DIR', '/home/kickpi/spatial-edgeav/runs/service'))

def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()

main_pid = run(['systemctl', 'show', service, '--property=MainPID', '--value'])
payload = {
    'platform': {
        'machine': platform.machine(),
        'system': platform.system(),
        'release': platform.release(),
        'python': platform.python_version(),
    },
    'uptime': run(['uptime']),
    'free_m': run(['free', '-m']),
    'df_h': run(['df', '-h', str(remote_run_dir)]),
    'main_pid': main_pid,
    'process': None,
    'thermal_zones': [],
}
if main_pid and main_pid != '0':
    payload['process'] = run(['ps', '-p', main_pid, '-o', 'pid,ppid,stat,etime,%cpu,%mem,rss,vsz,cmd'])

for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
    temp = zone / 'temp'
    typ = zone / 'type'
    if temp.exists():
        try:
            raw = int(temp.read_text().strip())
            celsius = raw / 1000.0
        except Exception:
            celsius = None
        payload['thermal_zones'].append({
            'zone': zone.name,
            'type': typ.read_text().strip() if typ.exists() else None,
            'temp_c': celsius,
        })

print(json.dumps(payload, indent=2))
PY" \
  > "${OUT_DIR}/resource_snapshot.json"

if retry_command scp -o BatchMode=yes -o ConnectTimeout=8 \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/rknn_camera_report.json" \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/rknn_camera_frames.json" \
  "${BOARD_HOST}:${REMOTE_RUN_DIR}/rknn_camera_last.jpg" \
  "${OUT_DIR}/" 2>/dev/null; then
  echo "Copied final service artifacts."
else
  echo "Final service artifacts are not available yet; service may still be running." >&2
fi

python3 - "${OUT_DIR}" "${SERVICE_NAME}" <<'PY'
import json
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
service = sys.argv[2]

def read_text(name: str) -> str:
    path = out_dir / name
    return path.read_text(encoding='utf-8').strip() if path.exists() else ''

def load_json(name: str) -> dict:
    path = out_dir / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

show = {}
for line in read_text('systemctl_show.env').splitlines():
    if '=' in line:
        key, value = line.split('=', 1)
        show[key] = value
heartbeat = load_json('heartbeat.json')
resources = load_json('resource_snapshot.json')

summary = {
    'service': service,
    'snapshot_dir': str(out_dir),
    'active': read_text('is_active.txt'),
    'systemd': show,
    'heartbeat': {
        'status': heartbeat.get('status'),
        'frames_processed': heartbeat.get('frames_processed'),
        'uptime_sec': heartbeat.get('uptime_sec'),
        'fps': heartbeat.get('fps'),
        'last_detection_count': (heartbeat.get('last_frame') or {}).get('detections_count'),
        'last_error': (heartbeat.get('last_frame') or {}).get('error'),
    },
    'resources': {
        'process': resources.get('process'),
        'thermal_zones': resources.get('thermal_zones', []),
    },
}
(out_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

fps = summary['heartbeat'].get('fps') or {}
lines = [
    '# RK3576 Service Snapshot',
    '',
    f'- Service: `{service}`',
    f'- Active: `{summary["active"]}`',
    f'- ActiveState: `{show.get("ActiveState", "-")}` / `{show.get("SubState", "-")}`',
    f'- MainPID: `{show.get("MainPID", "-")}`',
    f'- Frames processed: `{summary["heartbeat"].get("frames_processed", "-")}`',
    f'- Uptime seconds: `{summary["heartbeat"].get("uptime_sec", "-")}`',
    f'- Inference FPS: `{fps.get("inference_only", "-")}`',
    f'- End-to-end FPS: `{fps.get("end_to_end", "-")}`',
    f'- Last detection count: `{summary["heartbeat"].get("last_detection_count", "-")}`',
    f'- Last frame error: `{summary["heartbeat"].get("last_error", "-")}`',
    '',
    '## Process',
    '',
    '```text',
    summary['resources'].get('process') or 'unavailable',
    '```',
    '',
    '## Thermal',
    '',
]
thermal = summary['resources'].get('thermal_zones') or []
if thermal:
    for item in thermal:
        lines.append(f'- {item.get("zone")} {item.get("type")}: {item.get("temp_c")} C')
else:
    lines.append('- unavailable')
lines.append('')
(out_dir / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(lines))
PY

echo
echo "Wrote snapshot:"
echo "  ${OUT_DIR}/summary.md"
echo "  ${OUT_DIR}/summary.json"
