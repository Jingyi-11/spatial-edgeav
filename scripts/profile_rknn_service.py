#!/usr/bin/env python3
"""Profile the RK3576 RKNN systemd service over time.

The script samples service health, heartbeat FPS, process memory, and thermal
zones over SSH, then writes a local trend report under runs/.
"""

from __future__ import annotations

import argparse
import json
import shlex
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REMOTE_COLLECTOR = r"""
import json
import subprocess
from pathlib import Path

SERVICE_NAME = "__SERVICE_NAME__"
REMOTE_RUN_DIR = Path("__REMOTE_RUN_DIR__")

def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()

def parse_key_values(text):
    data = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key] = value
    return data

def parse_ps(text):
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    header = lines[0].split()
    values = lines[1].split(None, len(header) - 1)
    return dict(zip(header, values))

show = parse_key_values(run([
    "systemctl",
    "show",
    SERVICE_NAME,
    "--no-pager",
    "--property=ActiveState,SubState,MainPID,NRestarts,MemoryCurrent,CPUUsageNSec,ExecMainStartTimestamp",
]))

heartbeat = {}
heartbeat_path = REMOTE_RUN_DIR / "heartbeat.json"
if heartbeat_path.exists():
    try:
        heartbeat = json.loads(heartbeat_path.read_text())
    except Exception as exc:
        heartbeat = {"error": str(exc)}

main_pid = show.get("MainPID") or "0"
process = None
if main_pid != "0":
    process = parse_ps(run(["ps", "-p", main_pid, "-o", "pid,stat,etime,%cpu,%mem,rss,vsz,cmd"]))

thermal = []
for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
    temp = zone / "temp"
    typ = zone / "type"
    if not temp.exists():
        continue
    try:
        raw = int(temp.read_text().strip())
        temp_c = raw / 1000.0
    except Exception:
        temp_c = None
    thermal.append({
        "zone": zone.name,
        "type": typ.read_text().strip() if typ.exists() else None,
        "temp_c": temp_c,
    })

print(json.dumps({
    "systemd": show,
    "heartbeat": heartbeat,
    "process": process,
    "thermal_zones": thermal,
}))
"""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[idx], 3)


def numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "p95": None, "min": None, "max": None}
    return {
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": percentile(values, 95),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def run_remote_sample(board_host: str, service_name: str, remote_run_dir: str, timeout_sec: int) -> dict[str, Any]:
    code = REMOTE_COLLECTOR.replace("__SERVICE_NAME__", service_name).replace("__REMOTE_RUN_DIR__", remote_run_dir)
    remote_cmd = f"python3 -c {shlex.quote(code)}"
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout_sec}", board_host, remote_cmd],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(proc.stdout)


def build_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    def heartbeat_value(sample: dict[str, Any], *keys: str) -> Any:
        value: Any = sample.get("heartbeat", {})
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    inference_fps = [v for s in samples if (v := numeric(heartbeat_value(s, "fps", "inference_only"))) is not None]
    e2e_fps = [v for s in samples if (v := numeric(heartbeat_value(s, "fps", "end_to_end"))) is not None]
    frames = [v for s in samples if (v := numeric(heartbeat_value(s, "frames_processed"))) is not None]
    uptime = [v for s in samples if (v := numeric(heartbeat_value(s, "uptime_sec"))) is not None]
    rss_kb = [
        v
        for s in samples
        if isinstance(s.get("process"), dict) and (v := numeric(s["process"].get("RSS"))) is not None
    ]
    cpu_pct = [
        v
        for s in samples
        if isinstance(s.get("process"), dict) and (v := numeric(s["process"].get("%CPU"))) is not None
    ]

    thermal_by_type: dict[str, list[float]] = {}
    for sample in samples:
        for zone in sample.get("thermal_zones", []):
            typ = zone.get("type") or zone.get("zone") or "unknown"
            temp = numeric(zone.get("temp_c"))
            if temp is not None:
                thermal_by_type.setdefault(str(typ), []).append(temp)

    restart_counts = [
        int(v)
        for s in samples
        if (v := s.get("systemd", {}).get("NRestarts")) is not None and str(v).isdigit()
    ]
    active_states = [s.get("systemd", {}).get("ActiveState") for s in samples]
    sub_states = [s.get("systemd", {}).get("SubState") for s in samples]
    last_errors = [heartbeat_value(s, "last_frame", "error") for s in samples]

    frame_delta = round(frames[-1] - frames[0], 3) if len(frames) >= 2 else None
    uptime_delta = round(uptime[-1] - uptime[0], 3) if len(uptime) >= 2 else None
    rss_delta = round(rss_kb[-1] - rss_kb[0], 3) if len(rss_kb) >= 2 else None

    return {
        "samples": len(samples),
        "active_state_all_active": all(state == "active" for state in active_states),
        "sub_state_all_running": all(state == "running" for state in sub_states),
        "restart_count_start": restart_counts[0] if restart_counts else None,
        "restart_count_end": restart_counts[-1] if restart_counts else None,
        "restart_count_delta": (restart_counts[-1] - restart_counts[0]) if len(restart_counts) >= 2 else None,
        "frames_processed_start": frames[0] if frames else None,
        "frames_processed_end": frames[-1] if frames else None,
        "frames_processed_delta": frame_delta,
        "uptime_sec_start": uptime[0] if uptime else None,
        "uptime_sec_end": uptime[-1] if uptime else None,
        "uptime_sec_delta": uptime_delta,
        "inference_fps": summarize(inference_fps),
        "end_to_end_fps": summarize(e2e_fps),
        "process_cpu_pct": summarize(cpu_pct),
        "process_rss_kb": summarize(rss_kb),
        "process_rss_delta_kb": rss_delta,
        "thermal_c": {key: summarize(values) for key, values in sorted(thermal_by_type.items())},
        "last_frame_errors": sorted({str(error) for error in last_errors if error not in (None, "None")}),
    }


def render_markdown(args: argparse.Namespace, summary: dict[str, Any], out_dir: Path) -> str:
    npu = summary.get("thermal_c", {}).get("npu-thermal", {})
    lines = [
        "# RK3576 Service Profiling Report",
        "",
        f"- Board: `{args.board_host}`",
        f"- Service: `{args.service_name}`",
        f"- Duration: `{args.duration_sec}` sec",
        f"- Interval: `{args.interval_sec}` sec",
        f"- Samples: `{summary['samples']}`",
        f"- Active all samples: `{summary['active_state_all_active']}`",
        f"- Running all samples: `{summary['sub_state_all_running']}`",
        f"- Restart count delta: `{summary['restart_count_delta']}`",
        f"- Frames processed delta: `{summary['frames_processed_delta']}`",
        f"- Uptime delta: `{summary['uptime_sec_delta']}` sec",
        f"- End-to-end FPS mean: `{summary['end_to_end_fps']['mean']}`",
        f"- Inference FPS mean: `{summary['inference_fps']['mean']}`",
        f"- Process CPU mean: `{summary['process_cpu_pct']['mean']}` %",
        f"- RSS mean: `{summary['process_rss_kb']['mean']}` KB",
        f"- RSS delta: `{summary['process_rss_delta_kb']}` KB",
        f"- NPU temperature mean: `{npu.get('mean')}` C",
        f"- Last-frame errors: `{summary['last_frame_errors'] or []}`",
        "",
        "## Interpretation",
        "",
    ]
    healthy = (
        summary["active_state_all_active"]
        and summary["sub_state_all_running"]
        and summary.get("restart_count_delta") == 0
        and not summary["last_frame_errors"]
    )
    if healthy:
        lines.append("The RK3576 service remained active/running for the full profiling window with no restart-count increase and no last-frame errors.")
    else:
        lines.append("The profiling window found at least one health signal that needs review; inspect samples.json and journal output.")
    lines.extend(
        [
            "",
            "Raw local artifacts:",
            "",
            "```text",
            str(out_dir),
            "  samples.json",
            "  summary.json",
            "  summary.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board-host", default="rk3576")
    parser.add_argument("--service-name", default="spatial-edgeav-rknn.service")
    parser.add_argument("--remote-run-dir", default="/home/kickpi/spatial-edgeav/runs/service")
    parser.add_argument("--duration-sec", type=int, default=300)
    parser.add_argument("--interval-sec", type=int, default=30)
    parser.add_argument("--connect-timeout-sec", type=int, default=8)
    parser.add_argument("--out-root", type=Path, default=Path("runs/rk3576_service_profiles"))
    args = parser.parse_args()

    if args.duration_sec <= 0:
        raise SystemExit("--duration-sec must be positive")
    if args.interval_sec <= 0:
        raise SystemExit("--interval-sec must be positive")

    out_dir = args.out_root / utc_stamp()
    out_dir.mkdir(parents=True, exist_ok=True)

    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    sample_index = 0
    while True:
        sample_started = time.monotonic()
        sample = run_remote_sample(args.board_host, args.service_name, args.remote_run_dir, args.connect_timeout_sec)
        sample["sample_index"] = sample_index
        sample["local_elapsed_sec"] = round(sample_started - started, 3)
        sample["sampled_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        samples.append(sample)
        print(
            "sample={idx} elapsed={elapsed}s frames={frames} e2e_fps={fps}".format(
                idx=sample_index,
                elapsed=sample["local_elapsed_sec"],
                frames=sample.get("heartbeat", {}).get("frames_processed"),
                fps=(sample.get("heartbeat", {}).get("fps") or {}).get("end_to_end"),
            ),
            flush=True,
        )
        sample_index += 1

        elapsed = time.monotonic() - started
        if elapsed >= args.duration_sec:
            break
        sleep_for = min(args.interval_sec, args.duration_sec - elapsed)
        time.sleep(max(0.0, sleep_for))

    summary = build_summary(samples)
    (out_dir / "samples.json").write_text(json.dumps({"samples": samples}, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    markdown = render_markdown(args, summary, out_dir)
    (out_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
