#!/usr/bin/env python3
"""Convert YOLOv8 ONNX to RKNN for RK3576.

Run this inside WSL or another x86 Linux environment with rknn-toolkit2
installed. INT8 conversion requires a calibration dataset text file.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--target", default="rk3576")
    parser.add_argument("--quant", choices=["fp", "i8"], default="fp")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--mean", default="0,0,0")
    parser.add_argument("--std", default="255,255,255")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    try:
        from rknn.api import RKNN
    except Exception as exc:  # pragma: no cover - depends on vendor package
        print(
            "Could not import rknn.api. Install RKNN-Toolkit2 in WSL first.",
            file=sys.stderr,
        )
        print(f"Import error: {exc}", file=sys.stderr)
        return 3

    do_quant = args.quant == "i8"
    if do_quant and not args.dataset:
        print("--dataset is required for INT8 quantization", file=sys.stderr)
        return 2

    mean = [[float(v) for v in args.mean.split(",")]]
    std = [[float(v) for v in args.std.split(",")]]
    args.out.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    rknn = RKNN(verbose=True)

    ret = rknn.config(
        target_platform=args.target,
        mean_values=mean,
        std_values=std,
        optimization_level=3,
    )
    if ret != 0:
        print(f"rknn.config failed: {ret}", file=sys.stderr)
        return ret

    ret = rknn.load_onnx(model=str(args.onnx))
    if ret != 0:
        print(f"rknn.load_onnx failed: {ret}", file=sys.stderr)
        return ret

    ret = rknn.build(
        do_quantization=do_quant,
        dataset=str(args.dataset) if args.dataset else None,
    )
    if ret != 0:
        print(f"rknn.build failed: {ret}", file=sys.stderr)
        return ret

    ret = rknn.export_rknn(str(args.out))
    rknn.release()
    if ret != 0:
        print(f"rknn.export_rknn failed: {ret}", file=sys.stderr)
        return ret

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    report = {
        "onnx": str(args.onnx),
        "rknn": str(args.out),
        "target": args.target,
        "quant": args.quant,
        "dataset": str(args.dataset) if args.dataset else None,
        "elapsed_ms": elapsed_ms,
    }
    report_path = args.report or args.out.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
