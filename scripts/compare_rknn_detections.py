#!/usr/bin/env python3
"""Compare decoded FP and INT8 RKNN detections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    detections = payload.get("detections", [])
    by_class: dict[str, int] = {}
    for det in detections:
        name = str(det.get("class_name", det.get("class_id", "unknown")))
        by_class[name] = by_class.get(name, 0) + 1
    return {
        "count": len(detections),
        "by_class": by_class,
        "top": detections[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fp", required=True, type=Path)
    parser.add_argument("--i8", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    fp = read_json(args.fp)
    i8 = read_json(args.i8)
    fp_summary = summarize(fp)
    i8_summary = summarize(i8)
    comparison: dict[str, Any] = {
        "fp": fp_summary,
        "i8": i8_summary,
        "status": "match" if fp_summary["by_class"] == i8_summary["by_class"] else "mismatch",
        "notes": [],
    }
    if fp_summary["count"] > 0 and i8_summary["count"] == 0:
        comparison["notes"].append(
            "INT8 produced no decoded detections while FP produced detections; inspect quantization output scale or output dtype settings."
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
