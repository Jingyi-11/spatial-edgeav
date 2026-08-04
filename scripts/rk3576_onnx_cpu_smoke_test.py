#!/usr/bin/env python3
"""Board-side ONNX Runtime CPU smoke test for RK3576 YOLOv8n.

This is the CPU fallback counterpart to rk3576_rknn_smoke_test.py. It writes a
diagnostic JSON report even when ONNX Runtime is missing, so benchmark matrices
can distinguish measured results from pending environment work.
"""

from __future__ import annotations

import argparse
import glob
import importlib
import json
import platform
import statistics
import time
from pathlib import Path
from typing import Any


COCO80 = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]


def module_status(name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - board environment dependent
        return {"available": False, "error": str(exc)}
    return {"available": True, "version": getattr(module, "__version__", None)}


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[idx], 3)


def box_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def box_intersection_over_smaller_area(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    smaller = min(area_a, area_b)
    return inter / smaller if smaller > 0 else 0.0


def nms(detections: list[dict[str, Any]], iou_threshold: float, containment_threshold: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    pending = sorted(detections, key=lambda item: item["confidence"], reverse=True)
    while pending:
        current = pending.pop(0)
        kept.append(current)
        pending = [
            item
            for item in pending
            if item["class_id"] != current["class_id"]
            or (
                box_iou(item["bbox_xyxy"], current["bbox_xyxy"]) < iou_threshold
                and box_intersection_over_smaller_area(item["bbox_xyxy"], current["bbox_xyxy"])
                < containment_threshold
            )
        ]
    return kept


def build_input(image_path: Path | None, image_size: int) -> tuple[Any | None, str]:
    numpy_status = module_status("numpy")
    if not numpy_status["available"]:
        return None, "numpy is not installed"

    import numpy as np

    if image_path is None:
        return np.zeros((1, 3, image_size, image_size), dtype=np.float32), "dummy_zero_nchw"

    cv2_status = module_status("cv2")
    if not cv2_status["available"]:
        return None, "cv2 is required when --image is provided"

    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        return None, f"could not decode image: {image_path}"
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = cv2.resize(image, (image_size, image_size), interpolation=cv2.INTER_LINEAR)
    image = image.astype(np.float32) / 255.0
    image = np.transpose(image, (2, 0, 1))
    return np.expand_dims(image, axis=0), "image_rgb_resized_nchw_float32"


def summarize_outputs(outputs: list[Any]) -> dict[str, Any]:
    import numpy as np

    tensors = []
    for idx, output in enumerate(outputs):
        arr = np.asarray(output)
        item: dict[str, Any] = {
            "index": idx,
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "min": round(float(arr.min()), 6),
            "max": round(float(arr.max()), 6),
            "nonzero": int(np.count_nonzero(arr)),
        }
        tensors.append(item)

    pred = np.asarray(outputs[0])
    squeezed = np.squeeze(pred)
    if squeezed.shape[0] != 84 and squeezed.shape[-1] == 84:
        squeezed = squeezed.T
    summary: dict[str, Any] = {"tensors": tensors}
    if squeezed.shape[0] == 84:
        boxes = squeezed[:4, :]
        scores = squeezed[4:, :]
        summary["box"] = {
            "min": round(float(boxes.min()), 6),
            "max": round(float(boxes.max()), 6),
            "nonzero": int(np.count_nonzero(boxes)),
        }
        summary["class_scores"] = {
            "min": round(float(scores.min()), 6),
            "max": round(float(scores.max()), 6),
            "nonzero": int(np.count_nonzero(scores)),
        }
    return summary


def decode_yolov8(
    outputs: list[Any],
    image_path: Path,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
    containment_threshold: float,
    max_detections: int,
) -> tuple[dict[str, Any], Any]:
    import cv2
    import numpy as np

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise ValueError(f"could not decode image: {image_path}")
    height, width = image_bgr.shape[:2]

    pred = np.asarray(outputs[0])
    pred = np.squeeze(pred)
    if pred.shape[0] != 84 and pred.shape[-1] == 84:
        pred = pred.T
    if pred.shape[0] != 84:
        raise ValueError(f"unexpected YOLO output shape: {list(np.asarray(outputs[0]).shape)}")

    boxes = pred[:4, :].T.astype(float)
    scores = pred[4:, :].T.astype(float)
    class_ids = np.argmax(scores, axis=1)
    confidences = scores[np.arange(scores.shape[0]), class_ids]

    scale_x = width / float(image_size)
    scale_y = height / float(image_size)
    detections: list[dict[str, Any]] = []
    for idx, (box, class_id, confidence) in enumerate(zip(boxes, class_ids, confidences)):
        confidence = float(confidence)
        if confidence < conf_threshold:
            continue
        cx, cy, bw, bh = [float(v) for v in box]
        x1 = max(0.0, (cx - bw / 2.0) * scale_x)
        y1 = max(0.0, (cy - bh / 2.0) * scale_y)
        x2 = min(float(width), (cx + bw / 2.0) * scale_x)
        y2 = min(float(height), (cy + bh / 2.0) * scale_y)
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append(
            {
                "id": idx,
                "class_id": int(class_id),
                "class_name": COCO80[int(class_id)] if int(class_id) < len(COCO80) else str(class_id),
                "confidence": round(confidence, 4),
                "bbox_xyxy": [round(v, 2) for v in [x1, y1, x2, y2]],
                "bbox_xywh": [round(x1, 2), round(y1, 2), round(x2 - x1, 2), round(y2 - y1, 2)],
            }
        )

    detections = nms(detections, iou_threshold, containment_threshold)[:max_detections]
    for idx, det in enumerate(detections):
        det["id"] = idx

    annotated = image_bgr.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in det["bbox_xyxy"]]
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 160, 0), 2)
        cv2.putText(
            annotated,
            label,
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 160, 0),
            2,
            cv2.LINE_AA,
        )

    payload = {
        "source": str(image_path),
        "image": {"width": width, "height": height},
        "model": "onnx-yolov8n",
        "device": "rk3576-cpu",
        "postprocess": {
            "type": "yolov8_raw_head",
            "confidence_threshold": conf_threshold,
            "iou_threshold": iou_threshold,
            "containment_threshold": containment_threshold,
            "max_detections": max_detections,
        },
        "detections": detections,
    }
    return payload, annotated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=Path("rk3576_onnx_cpu_report.json"))
    parser.add_argument("--detections", type=Path, default=Path("rk3576_onnx_cpu_detections.json"))
    parser.add_argument("--annotated", type=Path, default=Path("rk3576_onnx_cpu_annotated.jpg"))
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--conf-threshold", type=float, default=0.25)
    parser.add_argument("--iou-threshold", type=float, default=0.45)
    parser.add_argument("--containment-threshold", type=float, default=0.85)
    parser.add_argument("--max-detections", type=int, default=100)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "status": "pending",
        "platform": {
            "machine": platform.machine(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        "model": {"path": str(args.model), "exists": args.model.exists()},
        "image": str(args.image) if args.image else None,
        "devices": {
            "rknpu": sorted(glob.glob("/dev/rknpu*")),
            "dri_render": sorted(glob.glob("/dev/dri/renderD*")),
        },
        "modules": {
            "numpy": module_status("numpy"),
            "cv2": module_status("cv2"),
            "onnxruntime": module_status("onnxruntime"),
        },
    }
    if args.model.exists():
        report["model"]["size_bytes"] = args.model.stat().st_size

    missing = [name for name, status in report["modules"].items() if not status["available"]]
    if missing:
        report["status"] = "missing_dependency"
        report["error"] = f"missing modules: {', '.join(missing)}"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    if not args.model.exists():
        report["status"] = "missing_model"
        report["error"] = f"missing ONNX model: {args.model}"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    input_tensor, input_source = build_input(args.image, args.image_size)
    if input_tensor is None:
        report["status"] = "input_error"
        report["error"] = input_source
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    import cv2
    import numpy as np
    import onnxruntime as ort

    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 4
    session_options.inter_op_num_threads = 1
    providers = ["CPUExecutionProvider"]
    session = ort.InferenceSession(str(args.model), sess_options=session_options, providers=providers)
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]

    for _ in range(args.warmup):
        session.run(output_names, {input_name: input_tensor})

    latencies = []
    outputs = None
    start_total = time.perf_counter()
    for _ in range(args.runs):
        start = time.perf_counter()
        outputs = session.run(output_names, {input_name: input_tensor})
        latencies.append((time.perf_counter() - start) * 1000.0)
    total_elapsed_ms = (time.perf_counter() - start_total) * 1000.0

    assert outputs is not None
    report.update(
        {
            "status": "ok",
            "runtime": {
                "engine": "onnxruntime",
                "providers": session.get_providers(),
                "input_name": input_name,
                "output_names": output_names,
                "threads": {"intra_op": 4, "inter_op": 1},
            },
            "input_source": input_source,
            "runs": args.runs,
            "warmup": args.warmup,
            "latency_ms": {
                "mean": round(statistics.mean(latencies), 3),
                "median": round(statistics.median(latencies), 3),
                "p95": percentile(latencies, 95),
                "min": round(min(latencies), 3),
                "max": round(max(latencies), 3),
            },
            "fps": round(1000.0 / statistics.mean(latencies), 3),
            "total_elapsed_ms": round(total_elapsed_ms, 3),
            "output_shapes": [list(np.asarray(output).shape) for output in outputs],
            "output_summary": summarize_outputs(outputs),
        }
    )

    if args.image is not None:
        try:
            detections_payload, annotated = decode_yolov8(
                outputs,
                args.image,
                args.image_size,
                args.conf_threshold,
                args.iou_threshold,
                args.containment_threshold,
                args.max_detections,
            )
            args.detections.parent.mkdir(parents=True, exist_ok=True)
            args.detections.write_text(json.dumps(detections_payload, indent=2), encoding="utf-8")
            args.annotated.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(args.annotated), annotated)
            report["detections"] = {
                "path": str(args.detections),
                "annotated": str(args.annotated),
                "count": len(detections_payload["detections"]),
                "error": None,
            }
        except Exception as exc:  # pragma: no cover - diagnostic path
            report["detections"] = {"count": None, "error": str(exc)}

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
