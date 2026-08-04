#!/usr/bin/env python3
"""Build a CPU/NPU/remote benchmark matrix from local Spatial EdgeAV reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_remote_run(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "latency.json").exists() and (path / "inference.json").exists()
    ]
    return sorted(candidates)[-1] if candidates else None


def mean_latency(report: dict[str, Any] | None) -> float | None:
    if not report:
        return None
    value = report.get("latency_ms", {}).get("mean")
    return float(value) if isinstance(value, int | float) else None


def fps_from_ms(ms: float | None) -> float | None:
    if not ms or ms <= 0:
        return None
    return round(1000.0 / ms, 3)


def fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        text = f"{value:.3f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text}{suffix}"


def model_size_mb(report: dict[str, Any] | None) -> float | None:
    if not report:
        return None
    size = report.get("model", {}).get("size_bytes")
    if not isinstance(size, int | float):
        return None
    return round(size / (1024 * 1024), 2)


def detection_count(report: dict[str, Any] | None) -> int | None:
    if not report:
        return None
    detections = report.get("detections", {})
    count = detections.get("count")
    return int(count) if isinstance(count, int | float) else None


def build_matrix(root: Path) -> dict[str, Any]:
    fp = load_json(root / "runs/rk3576_board/yolov8n_rk3576_fp_rk3576_report.json")
    raw_i8 = load_json(root / "runs/rk3576_board/yolov8n_rk3576_i8_rk3576_report.json")
    rockchip_i8 = load_json(root / "runs/rk3576_board/yolov8n_rockchip_rk3576_i8_rk3576_report.json")
    camera = load_json(root / "runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_camera_report.json")

    remote_dir = latest_remote_run(root / "runs/edgeav_remote_yolo")
    remote_latency = load_json(remote_dir / "latency.json") if remote_dir else None
    remote_inference = load_json(remote_dir / "inference.json") if remote_dir else None

    rows: list[dict[str, Any]] = []

    def add_report_row(
        *,
        name: str,
        engine: str,
        device: str,
        model: str,
        precision: str,
        workload: str,
        report: dict[str, Any] | None,
        quality: str,
        notes: str,
    ) -> None:
        latency = mean_latency(report)
        rows.append(
            {
                "name": name,
                "status": "measured" if report else "pending",
                "engine": engine,
                "device": device,
                "model": model,
                "precision": precision,
                "workload": workload,
                "model_size_mb": model_size_mb(report),
                "latency_mean_ms": latency,
                "fps": report.get("fps") if report and isinstance(report.get("fps"), int | float) else fps_from_ms(latency),
                "detections": detection_count(report),
                "quality": quality if report else "pending",
                "notes": notes,
            }
        )

    add_report_row(
        name="RK3576 NPU single image FP",
        engine="RKNN Runtime / Lite2",
        device="RK3576 RKNPU",
        model="Ultralytics YOLOv8n export",
        precision="FP",
        workload="single image, 30 timed runs",
        report=fp,
        quality="accepted baseline",
        notes="Reference RKNN path; slower but class scores and detections are valid.",
    )
    add_report_row(
        name="RK3576 NPU single image INT8 raw head",
        engine="RKNN Runtime / Lite2",
        device="RK3576 RKNPU",
        model="Ultralytics YOLOv8n one-output ONNX",
        precision="INT8",
        workload="single image, 30 timed runs",
        report=raw_i8,
        quality="rejected",
        notes="Fast, but class-score channels quantize to zero, so detection quality fails.",
    )
    add_report_row(
        name="RK3576 NPU single image INT8 optimized head",
        engine="RKNN Runtime / Lite2",
        device="RK3576 RKNPU",
        model="Rockchip optimized YOLOv8n ONNX",
        precision="INT8",
        workload="single image, 30 timed runs",
        report=rockchip_i8,
        quality="accepted deployable baseline",
        notes="Uses 9-output box/class/score-sum head; preserves meaningful detections.",
    )

    if camera:
        e2e = camera["latency_ms"]["end_to_end"]["mean"]
        rows.append(
            {
                "name": "RK3576 NPU continuous camera INT8",
                "status": "measured",
                "engine": "OpenCV/V4L2 + RKNN Runtime / Lite2",
                "device": "RK3576 C920 + RKNPU",
                "model": "Rockchip optimized YOLOv8n RKNN",
                "precision": "INT8",
                "workload": f"{camera.get('frames_processed', 0)} camera frames",
                "model_size_mb": model_size_mb(camera),
                "latency_mean_ms": round(float(e2e), 3),
                "fps": camera.get("fps", {}).get("end_to_end"),
                "detections": sum(camera.get("detections", {}).get("by_class", {}).values()),
                "quality": "accepted runtime baseline",
                "notes": "Includes capture, preprocess, NPU inference, candidate-filtered DFL/NMS, JSON frame output.",
                "breakdown_ms": {
                    key: value["mean"]
                    for key, value in camera.get("latency_ms", {}).items()
                    if isinstance(value, dict) and "mean" in value
                },
            }
        )
    else:
        rows.append(
            {
                "name": "RK3576 NPU continuous camera INT8",
                "status": "pending",
                "engine": "OpenCV/V4L2 + RKNN Runtime / Lite2",
                "device": "RK3576 C920 + RKNPU",
                "model": "Rockchip optimized YOLOv8n RKNN",
                "precision": "INT8",
                "workload": "continuous camera frames",
                "model_size_mb": None,
                "latency_mean_ms": None,
                "fps": None,
                "detections": None,
                "quality": "pending",
                "notes": "Run make run-rknn-camera-board.",
            }
        )

    if remote_latency and remote_inference:
        model_ms = remote_latency.get("model_ms", {})
        inference_ms = model_ms.get("inference")
        total_ms = remote_latency.get("total_ms")
        rows.append(
            {
                "name": "WSL CPU YOLO core inference",
                "status": "measured",
                "engine": "Ultralytics / PyTorch CPU",
                "device": "Windows WSL2 x86 CPU",
                "model": "YOLOv8n",
                "precision": "FP32 CPU",
                "workload": f"single image from {remote_dir.name}",
                "model_size_mb": None,
                "latency_mean_ms": inference_ms,
                "fps": fps_from_ms(float(inference_ms)) if isinstance(inference_ms, int | float) else None,
                "detections": remote_latency.get("detections_count"),
                "quality": "validation baseline",
                "notes": "Pure Ultralytics inference time; excludes SSH/SCP orchestration.",
                "breakdown_ms": model_ms,
            }
        )
        rows.append(
            {
                "name": "Mac -> RK3576 -> WSL remote pipeline",
                "status": "measured",
                "engine": "SSH/SCP + Windows bridge + Ultralytics CPU",
                "device": "Distributed Mac/RK3576/Windows",
                "model": "YOLOv8n",
                "precision": "FP32 CPU",
                "workload": f"single end-to-end smoke run from {remote_dir.name}",
                "model_size_mb": None,
                "latency_mean_ms": total_ms,
                "fps": fps_from_ms(float(total_ms)) if isinstance(total_ms, int | float) else None,
                "detections": remote_latency.get("detections_count"),
                "quality": "connectivity baseline",
                "notes": "Measures orchestration overhead, not only model compute.",
                "breakdown_ms": remote_latency.get("steps_ms", {}),
            }
        )

    rows.extend(
        [
            {
                "name": "RK3576 CPU ONNX Runtime",
                "status": "pending",
                "engine": "ONNX Runtime CPU",
                "device": "RK3576 ARM CPU",
                "model": "YOLOv8n ONNX",
                "precision": "FP32 or INT8 CPU EP",
                "workload": "single image and camera loop",
                "model_size_mb": None,
                "latency_mean_ms": None,
                "fps": None,
                "detections": None,
                "quality": "pending",
                "notes": "Useful as a board-local CPU fallback; package/runtime not benchmarked yet.",
            },
            {
                "name": "MacBook M1 CPU/ANE reference",
                "status": "pending",
                "engine": "PyTorch, ONNX Runtime, or Core ML",
                "device": "MacBook M1",
                "model": "YOLOv8n",
                "precision": "FP32/FP16 depending backend",
                "workload": "single image validation",
                "model_size_mb": None,
                "latency_mean_ms": None,
                "fps": None,
                "detections": None,
                "quality": "pending",
                "notes": "Optional host-side reference; not required for RK3576 deployment.",
            },
        ]
    )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_root": str(root),
        "matrix": rows,
    }


def render_markdown(matrix: dict[str, Any]) -> str:
    rows = matrix["matrix"]
    lines = [
        "# Benchmark Matrix",
        "",
        "This file is generated from local JSON reports by:",
        "",
        "```bash",
        "make benchmark-matrix",
        "```",
        "",
        f"Generated at: `{matrix['generated_at_utc']}`",
        "",
        "## Summary",
        "",
        "| Path | Status | Device | Precision | Workload | Mean latency | FPS | Detections | Quality |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {name} | {status} | {device} | {precision} | {workload} | {latency} | {fps} | {detections} | {quality} |".format(
                name=row["name"],
                status=row["status"],
                device=row["device"],
                precision=row["precision"],
                workload=row["workload"],
                latency=fmt(row.get("latency_mean_ms"), " ms"),
                fps=fmt(row.get("fps")),
                detections=fmt(row.get("detections")),
                quality=row["quality"],
            )
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
        ]
    )
    for row in rows:
        lines.append(f"- **{row['name']}**: {row['notes']}")
        breakdown = row.get("breakdown_ms")
        if breakdown:
            detail = ", ".join(f"{key}={fmt(value, ' ms')}" for key, value in breakdown.items())
            lines.append(f"  Breakdown: {detail}.")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The RK3576 NPU INT8 optimized-head path is the current deployable edge baseline.",
            "- The raw Ultralytics INT8 RKNN is kept as a documented failed optimization because its class-score branch collapses to zero.",
            "- The WSL CPU number is useful for model validation, while the remote pipeline number measures SSH/SCP orchestration overhead.",
            "- Phase 3 CPU coverage is not fully complete until RK3576 CPU ONNX Runtime and optional MacBook reference benchmarks are added.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json-out", type=Path, default=Path("runs/benchmarks/benchmark_matrix.json"))
    parser.add_argument("--md-out", type=Path, default=Path("docs/benchmark_matrix.md"))
    args = parser.parse_args()

    root = args.root.resolve()
    matrix = build_matrix(root)

    json_out = (root / args.json_out).resolve() if not args.json_out.is_absolute() else args.json_out
    md_out = (root / args.md_out).resolve() if not args.md_out.is_absolute() else args.md_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    md_out.write_text(render_markdown(matrix), encoding="utf-8")

    print(f"Wrote {json_out}")
    print(f"Wrote {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
