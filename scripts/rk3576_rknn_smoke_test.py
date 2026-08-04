#!/usr/bin/env python3
"""Board-side RKNN smoke test and benchmark helper for RK3576.

The script is intentionally diagnostic-first: it writes a JSON report even when
RKNN Lite, NumPy, image decoding, or NPU device nodes are missing on the board.
"""

from __future__ import annotations

import argparse
import glob
import importlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any


def module_status(name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - board environment dependent
        return {"available": False, "error": str(exc)}
    return {"available": True, "version": getattr(module, "__version__", None)}


def build_input(image_path: Path | None, image_size: int) -> tuple[Any | None, str]:
    numpy_status = module_status("numpy")
    if not numpy_status["available"]:
        return None, "numpy is not installed"

    import numpy as np

    if image_path is None:
        return np.zeros((1, image_size, image_size, 3), dtype=np.uint8), "dummy_zero"

    cv2_status = module_status("cv2")
    if not cv2_status["available"]:
        return None, "cv2 is required when --image is provided"

    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        return None, f"could not decode image: {image_path}"
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = cv2.resize(image, (image_size, image_size), interpolation=cv2.INTER_LINEAR)
    return np.expand_dims(image, axis=0), "image_rgb_resized"


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[idx], 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=Path("rk3576_rknn_report.json"))
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument(
        "--fail-on-missing-runtime",
        action="store_true",
        help="Return non-zero when RKNN Lite is missing instead of writing a diagnostic-only report.",
    )
    args = parser.parse_args()

    args.report.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "status": "not_started",
        "platform": {
            "machine": platform.machine(),
            "system": platform.system(),
            "release": platform.release(),
            "python": sys.version.split()[0],
        },
        "model": {
            "path": str(args.model),
            "exists": args.model.exists(),
            "size_bytes": args.model.stat().st_size if args.model.exists() else None,
        },
        "image": str(args.image) if args.image else None,
        "devices": {
            "rknpu": glob.glob("/dev/rknpu*"),
            "dri_render": glob.glob("/dev/dri/renderD*"),
        },
        "modules": {
            "numpy": module_status("numpy"),
            "cv2": module_status("cv2"),
            "rknnlite": module_status("rknnlite"),
        },
    }

    def finish(status: str, exit_code: int = 0, **extra: Any) -> int:
        report["status"] = status
        report.update(extra)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return exit_code

    if not args.model.exists():
        return finish("missing_model", 2)

    if not report["modules"]["rknnlite"]["available"]:
        code = 3 if args.fail_on_missing_runtime else 0
        return finish("missing_rknn_lite", code)

    input_tensor, input_source = build_input(args.image, args.image_size)
    if input_tensor is None:
        return finish("missing_input_dependency", 4, input_error=input_source)

    try:
        from rknnlite.api import RKNNLite
    except Exception as exc:  # pragma: no cover - board environment dependent
        return finish("missing_rknn_lite", 3, runtime_error=str(exc))

    rknn = RKNNLite(verbose=False)
    started = time.perf_counter()
    ret = rknn.load_rknn(str(args.model))
    if ret != 0:
        rknn.release()
        return finish("load_rknn_failed", 5, rknn_ret=ret)

    ret = rknn.init_runtime()
    if ret != 0:
        rknn.release()
        return finish("init_runtime_failed", 6, rknn_ret=ret)

    for _ in range(args.warmup):
        rknn.inference(inputs=[input_tensor])

    latencies_ms: list[float] = []
    output_shapes: list[list[int]] = []
    for _ in range(args.runs):
        t0 = time.perf_counter()
        outputs = rknn.inference(inputs=[input_tensor])
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if outputs and not output_shapes:
            output_shapes = [list(getattr(output, "shape", [])) for output in outputs]

    rknn.release()
    total_ms = (time.perf_counter() - started) * 1000.0
    avg_ms = statistics.mean(latencies_ms) if latencies_ms else None
    fps = 1000.0 / avg_ms if avg_ms else None

    return finish(
        "ok",
        0,
        input_source=input_source,
        runs=args.runs,
        warmup=args.warmup,
        latency_ms={
            "mean": round(avg_ms, 3) if avg_ms else None,
            "median": round(statistics.median(latencies_ms), 3) if latencies_ms else None,
            "p95": percentile(latencies_ms, 95),
            "min": round(min(latencies_ms), 3) if latencies_ms else None,
            "max": round(max(latencies_ms), 3) if latencies_ms else None,
        },
        fps=round(fps, 3) if fps else None,
        total_elapsed_ms=round(total_ms, 3),
        output_shapes=output_shapes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
