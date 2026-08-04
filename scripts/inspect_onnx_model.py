#!/usr/bin/env python3
"""Write a small JSON report for an ONNX model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import onnx


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: inspect_onnx_model.py <model.onnx> <report.json>", file=sys.stderr)
        return 2

    onnx_path = Path(sys.argv[1])
    report_path = Path(sys.argv[2])
    model = onnx.load(str(onnx_path))
    payload = {
        "onnx_path": str(onnx_path),
        "size_bytes": onnx_path.stat().st_size,
        "ir_version": model.ir_version,
        "opset": [op.version for op in model.opset_import],
        "inputs": [value.name for value in model.graph.input],
        "outputs": [value.name for value in model.graph.output],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
