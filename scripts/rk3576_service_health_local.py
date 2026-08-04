#!/usr/bin/env python3
"""Run a local health check for the RK3576 Spatial EdgeAV service."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()


def numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_key_values(text: str) -> dict[str, str]:
    data = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key] = value
    return data


def parse_ps(text: str) -> dict[str, str] | None:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    header = lines[0].split()
    values = lines[1].split(None, len(header) - 1)
    return dict(zip(header, values))


def collect_sample(service_name: str, run_dir: Path) -> dict[str, Any]:
    show = parse_key_values(
        run(
            [
                "systemctl",
                "show",
                service_name,
                "--no-pager",
                "--property=ActiveState,SubState,MainPID,NRestarts,MemoryCurrent,CPUUsageNSec,ExecMainStartTimestamp",
            ]
        )
    )

    heartbeat_path = run_dir / "heartbeat.json"
    heartbeat = {}
    heartbeat_mtime = None
    if heartbeat_path.exists():
        heartbeat_mtime = heartbeat_path.stat().st_mtime
        try:
            heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report parse failures as health data.
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
            temp_c = int(temp.read_text(encoding="utf-8").strip()) / 1000.0
        except Exception:  # noqa: BLE001 - missing or unusual thermal nodes should not crash health collection.
            temp_c = None
        thermal.append(
            {
                "zone": zone.name,
                "type": typ.read_text(encoding="utf-8").strip() if typ.exists() else None,
                "temp_c": temp_c,
            }
        )

    return {
        "host_time_sec": time.time(),
        "systemd": show,
        "heartbeat": heartbeat,
        "heartbeat_mtime_sec": heartbeat_mtime,
        "process": process,
        "thermal_zones": thermal,
    }


def evaluate(sample: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, message: str, value: Any = None, threshold: Any = None) -> None:
        checks.append(
            {
                "name": name,
                "status": status,
                "message": message,
                "value": value,
                "threshold": threshold,
            }
        )

    systemd = sample.get("systemd", {})
    heartbeat = sample.get("heartbeat", {})
    process = sample.get("process") or {}

    active_state = systemd.get("ActiveState")
    sub_state = systemd.get("SubState")
    add(
        "systemd_active",
        "ok" if active_state == "active" and sub_state == "running" else "critical",
        f"systemd state is {active_state}/{sub_state}",
        {"ActiveState": active_state, "SubState": sub_state},
        "active/running",
    )

    main_pid = systemd.get("MainPID")
    add("main_pid", "ok" if main_pid and main_pid != "0" else "critical", f"MainPID is {main_pid}", main_pid, "nonzero")

    heartbeat_error = heartbeat.get("error")
    add(
        "heartbeat_parse",
        "ok" if not heartbeat_error and heartbeat else "critical",
        "heartbeat JSON is readable" if not heartbeat_error and heartbeat else f"heartbeat error: {heartbeat_error}",
        heartbeat_error,
        "valid JSON",
    )

    heartbeat_age = None
    host_time = numeric(sample.get("host_time_sec"))
    mtime = numeric(sample.get("heartbeat_mtime_sec"))
    if host_time is not None and mtime is not None:
        heartbeat_age = round(host_time - mtime, 3)
    add(
        "heartbeat_age",
        "ok" if heartbeat_age is not None and heartbeat_age <= args.max_heartbeat_age_sec else "critical",
        f"heartbeat age is {heartbeat_age} sec",
        heartbeat_age,
        f"<= {args.max_heartbeat_age_sec} sec",
    )

    restart_count = numeric(systemd.get("NRestarts"))
    add(
        "restart_count",
        "ok" if restart_count is not None and restart_count <= args.max_restarts else "critical",
        f"restart count is {restart_count}",
        restart_count,
        f"<= {args.max_restarts}",
    )

    e2e_fps = numeric((heartbeat.get("fps") or {}).get("end_to_end"))
    add(
        "end_to_end_fps",
        "ok" if e2e_fps is not None and e2e_fps >= args.min_e2e_fps else "critical",
        f"end-to-end FPS is {e2e_fps}",
        e2e_fps,
        f">= {args.min_e2e_fps}",
    )

    last_error = (heartbeat.get("last_frame") or {}).get("error")
    add("last_frame_error", "ok" if last_error in (None, "None") else "critical", f"last frame error is {last_error}", last_error, "None")

    rss_kb = numeric(process.get("RSS"))
    add("process_rss", "ok" if rss_kb is not None and rss_kb <= args.max_rss_kb else "warn", f"RSS is {rss_kb} KB", rss_kb, f"<= {args.max_rss_kb} KB")

    thermal = sample.get("thermal_zones", [])
    max_temp = max([t for zone in thermal if (t := numeric(zone.get("temp_c"))) is not None], default=None)
    add(
        "max_temperature",
        "ok" if max_temp is not None and max_temp <= args.max_temp_c else "warn",
        f"max thermal-zone temperature is {max_temp} C",
        max_temp,
        f"<= {args.max_temp_c} C",
    )

    severities = [item["status"] for item in checks]
    if "critical" in severities:
        overall = "critical"
    elif "warn" in severities:
        overall = "warn"
    else:
        overall = "ok"

    return {
        "overall": overall,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {
            "max_heartbeat_age_sec": args.max_heartbeat_age_sec,
            "max_restarts": args.max_restarts,
            "min_e2e_fps": args.min_e2e_fps,
            "max_rss_kb": args.max_rss_kb,
            "max_temp_c": args.max_temp_c,
        },
        "checks": checks,
        "sample": sample,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RK3576 Local Service Health Check",
        "",
        f"- Overall: `{report['overall']}`",
        f"- Checked at: `{report['checked_at_utc']}`",
        "",
        "| Check | Status | Value | Threshold | Message |",
        "|---|---|---:|---:|---|",
    ]
    for item in report["checks"]:
        lines.append(
            "| {name} | {status} | {value} | {threshold} | {message} |".format(
                name=item["name"],
                status=item["status"],
                value=item.get("value"),
                threshold=item.get("threshold"),
                message=item["message"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-name", default="spatial-edgeav-rknn.service")
    parser.add_argument("--run-dir", type=Path, default=Path("/home/kickpi/spatial-edgeav/runs/service"))
    parser.add_argument("--out-dir", type=Path, default=Path("/home/kickpi/spatial-edgeav/runs/service_health"))
    parser.add_argument("--max-heartbeat-age-sec", type=float, default=30.0)
    parser.add_argument("--max-restarts", type=int, default=0)
    parser.add_argument("--min-e2e-fps", type=float, default=10.0)
    parser.add_argument("--max-rss-kb", type=float, default=600000.0)
    parser.add_argument("--max-temp-c", type=float, default=75.0)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    sample = collect_sample(args.service_name, args.run_dir)
    report = evaluate(sample, args)
    (args.out_dir / "health.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.out_dir / "health.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "checked_at_utc": report["checked_at_utc"]}))
    return 0 if report["overall"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
