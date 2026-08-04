#!/usr/bin/env python3
"""Compare two RK3576 RKNN benchmark reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fp", required=True, type=Path)
    parser.add_argument("--i8", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    fp = load_report(args.fp)
    i8 = load_report(args.i8)

    fp_mean = fp["latency_ms"]["mean"]
    i8_mean = i8["latency_ms"]["mean"]
    fp_size = fp["model"]["size_bytes"]
    i8_size = i8["model"]["size_bytes"]

    comparison = {
        "fp": {
            "model_size_bytes": fp_size,
            "latency_mean_ms": fp_mean,
            "fps": fp["fps"],
            "output_shapes": fp.get("output_shapes", []),
        },
        "i8": {
            "model_size_bytes": i8_size,
            "latency_mean_ms": i8_mean,
            "fps": i8["fps"],
            "output_shapes": i8.get("output_shapes", []),
        },
        "improvement": {
            "latency_speedup": round(fp_mean / i8_mean, 3),
            "latency_reduction_pct": round((1.0 - i8_mean / fp_mean) * 100.0, 2),
            "fps_gain_pct": round((i8["fps"] / fp["fps"] - 1.0) * 100.0, 2),
            "model_size_reduction_pct": round((1.0 - i8_size / fp_size) * 100.0, 2),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
