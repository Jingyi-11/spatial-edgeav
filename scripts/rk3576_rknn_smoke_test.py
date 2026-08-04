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


def nms(detections: list[dict[str, Any]], iou_threshold: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    pending = sorted(detections, key=lambda item: item["confidence"], reverse=True)
    while pending:
        current = pending.pop(0)
        kept.append(current)
        pending = [
            item
            for item in pending
            if item["class_id"] != current["class_id"]
            or box_iou(item["bbox_xyxy"], current["bbox_xyxy"]) < iou_threshold
        ]
    return kept


def summarize_yolo_output(outputs: list[Any]) -> dict[str, Any]:
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
        if arr.ndim == 4 and arr.shape[1] in (1, 64, 80):
            item["role_hint"] = {1: "score_sum", 64: "box_distribution", 80: "class_scores"}[arr.shape[1]]
        tensors.append(item)

    pred = np.asarray(outputs[0])
    squeezed = np.squeeze(pred)
    if squeezed.shape[0] != 84 and squeezed.shape[-1] == 84:
        squeezed = squeezed.T
    summary: dict[str, Any] = {
        "tensors": tensors,
        "shape": list(pred.shape),
        "dtype": str(pred.dtype),
        "min": round(float(pred.min()), 6),
        "max": round(float(pred.max()), 6),
    }
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


def softmax_numpy(values: Any, axis: int) -> Any:
    import numpy as np

    shifted = values - np.max(values, axis=axis, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=axis, keepdims=True)


def dfl(position: Any) -> Any:
    import numpy as np

    n, channels, height, width = position.shape
    bins = channels // 4
    position = position.reshape(n, 4, bins, height, width)
    weights = np.arange(bins, dtype=np.float32).reshape(1, 1, bins, 1, 1)
    return (softmax_numpy(position, axis=2) * weights).sum(axis=2)


def box_process(position: Any, image_size: int) -> Any:
    import numpy as np

    _, _, grid_h, grid_w = position.shape
    col, row = np.meshgrid(np.arange(grid_w), np.arange(grid_h))
    grid = np.stack((col, row), axis=0).reshape(1, 2, grid_h, grid_w).astype(np.float32)
    stride = np.array([image_size / grid_w, image_size / grid_h], dtype=np.float32).reshape(1, 2, 1, 1)
    distances = dfl(position.astype(np.float32))
    box_xy = grid + 0.5 - distances[:, 0:2, :, :]
    box_xy2 = grid + 0.5 + distances[:, 2:4, :, :]
    return np.concatenate((box_xy * stride, box_xy2 * stride), axis=1)


def box_process_selected(position: Any, candidate_mask: Any, image_size: int) -> Any:
    import numpy as np

    _, channels, grid_h, grid_w = position.shape
    bins = channels // 4
    ys, xs = np.nonzero(candidate_mask)
    if len(xs) == 0:
        return np.empty((0, 4), dtype=np.float32)

    logits = position[0, :, ys, xs].T.astype(np.float32).reshape(-1, 4, bins)
    weights = np.arange(bins, dtype=np.float32).reshape(1, 1, bins)
    distances = (softmax_numpy(logits, axis=2) * weights).sum(axis=2)
    grid = np.stack((xs, ys), axis=1).astype(np.float32) + 0.5
    stride = np.array([image_size / grid_w, image_size / grid_h], dtype=np.float32)
    top_left = (grid - distances[:, 0:2]) * stride
    bottom_right = (grid + distances[:, 2:4]) * stride
    return np.concatenate((top_left, bottom_right), axis=1)


def flatten_hw_channels(tensor: Any) -> Any:
    import numpy as np

    return np.transpose(tensor, (0, 2, 3, 1)).reshape(-1, tensor.shape[1]).astype(np.float32)


def group_rockchip_yolov8_outputs(outputs: list[Any]) -> list[tuple[Any, Any, Any | None]]:
    import numpy as np

    tensors = [np.asarray(output) for output in outputs]
    four_dim = [tensor for tensor in tensors if tensor.ndim == 4]
    groups: list[tuple[Any, Any, Any | None]] = []
    sizes = sorted({(tensor.shape[2], tensor.shape[3]) for tensor in four_dim}, reverse=True)
    for height, width in sizes:
        same_grid = [tensor for tensor in four_dim if tensor.shape[2] == height and tensor.shape[3] == width]
        box = next((tensor for tensor in same_grid if tensor.shape[1] == 64), None)
        scores = next((tensor for tensor in same_grid if tensor.shape[1] == 80), None)
        score_sum = next((tensor for tensor in same_grid if tensor.shape[1] == 1), None)
        if box is not None and scores is not None:
            groups.append((box, scores, score_sum))
    return groups


def decode_rockchip_yolov8(
    outputs: list[Any],
    image_path: Path,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
    max_detections: int,
) -> tuple[dict[str, Any], Any]:
    import cv2
    import numpy as np

    groups = group_rockchip_yolov8_outputs(outputs)
    if not groups:
        raise ValueError("no Rockchip YOLOv8 output groups found")

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise ValueError(f"could not decode image: {image_path}")
    height, width = image_bgr.shape[:2]

    box_arrays = []
    score_arrays = []
    candidate_stats = []
    for box_tensor, score_tensor, score_sum in groups:
        scores = flatten_hw_channels(score_tensor)
        class_confidences = np.max(scores, axis=1)
        candidate_mask = class_confidences.reshape(score_tensor.shape[2], score_tensor.shape[3]) >= conf_threshold
        if score_sum is not None:
            sum_scores = flatten_hw_channels(score_sum)[:, 0]
            candidate_mask &= sum_scores.reshape(score_sum.shape[2], score_sum.shape[3]) >= conf_threshold
        boxes = box_process_selected(box_tensor, candidate_mask, image_size)
        if boxes.size == 0:
            candidate_stats.append(
                {
                    "grid": [int(score_tensor.shape[2]), int(score_tensor.shape[3])],
                    "positions": int(score_tensor.shape[2] * score_tensor.shape[3]),
                    "candidates": 0,
                }
            )
            continue
        box_arrays.append(boxes)
        score_arrays.append(scores[candidate_mask.reshape(-1)])
        candidate_stats.append(
            {
                "grid": [int(score_tensor.shape[2]), int(score_tensor.shape[3])],
                "positions": int(score_tensor.shape[2] * score_tensor.shape[3]),
                "candidates": int(np.count_nonzero(candidate_mask)),
            }
        )

    boxes = np.concatenate(box_arrays, axis=0) if box_arrays else np.empty((0, 4), dtype=np.float32)
    scores = np.concatenate(score_arrays, axis=0) if score_arrays else np.empty((0, 80), dtype=np.float32)
    if boxes.size == 0 or scores.size == 0:
        class_ids = np.empty((0,), dtype=np.int64)
        confidences = np.empty((0,), dtype=np.float32)
    else:
        class_ids = np.argmax(scores, axis=1)
        confidences = scores[np.arange(scores.shape[0]), class_ids]

    scale_x = width / float(image_size)
    scale_y = height / float(image_size)
    detections: list[dict[str, Any]] = []
    for idx, (box, class_id, confidence) in enumerate(zip(boxes, class_ids, confidences)):
        confidence = float(confidence)
        if confidence < conf_threshold:
            continue
        x1, y1, x2, y2 = [float(v) for v in box]
        x1 = max(0.0, min(float(width), x1 * scale_x))
        y1 = max(0.0, min(float(height), y1 * scale_y))
        x2 = max(0.0, min(float(width), x2 * scale_x))
        y2 = max(0.0, min(float(height), y2 * scale_y))
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

    detections = nms(detections, iou_threshold)[:max_detections]
    for idx, det in enumerate(detections):
        det["id"] = idx

    annotated = image_bgr.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in det["bbox_xyxy"]]
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 180, 255), 2)
        cv2.putText(
            annotated,
            label,
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 180, 255),
            2,
            cv2.LINE_AA,
        )

    payload = {
        "source": str(image_path),
        "image": {"width": width, "height": height},
        "model": "rknn-yolov8n-rockchip-optimized",
        "device": "rk3576-rknn",
        "postprocess": {
            "type": "rockchip_yolov8_optimized_head",
            "output_groups": len(groups),
            "candidate_filter": "class_score_and_score_sum",
            "candidate_stats": candidate_stats,
            "confidence_threshold": conf_threshold,
            "iou_threshold": iou_threshold,
            "max_detections": max_detections,
        },
        "detections": detections,
    }
    return payload, annotated


def decode_outputs(
    outputs: list[Any],
    image_path: Path,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
    max_detections: int,
) -> tuple[dict[str, Any], Any]:
    import numpy as np

    if group_rockchip_yolov8_outputs(outputs):
        return decode_rockchip_yolov8(
            outputs,
            image_path,
            image_size,
            conf_threshold,
            iou_threshold,
            max_detections,
        )
    pred = np.asarray(outputs[0])
    squeezed = np.squeeze(pred)
    if squeezed.shape[0] == 84 or squeezed.shape[-1] == 84:
        return decode_yolov8(outputs, image_path, image_size, conf_threshold, iou_threshold, max_detections)
    raise ValueError(f"unsupported output shapes: {[list(np.asarray(output).shape) for output in outputs]}")


def decode_yolov8(
    outputs: list[Any],
    image_path: Path,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
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

    detections = nms(detections, iou_threshold)[:max_detections]
    for idx, det in enumerate(detections):
        det["id"] = idx

    annotated = image_bgr.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in det["bbox_xyxy"]]
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 220, 80), 2)
        cv2.putText(
            annotated,
            label,
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 220, 80),
            2,
            cv2.LINE_AA,
        )

    payload = {
        "source": str(image_path),
        "image": {"width": width, "height": height},
        "model": "rknn-yolov8n",
        "device": "rk3576-rknn",
        "postprocess": {
            "type": "yolov8_raw_head",
            "confidence_threshold": conf_threshold,
            "iou_threshold": iou_threshold,
            "max_detections": max_detections,
        },
        "detections": detections,
    }
    return payload, annotated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--image", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=Path("rk3576_rknn_report.json"))
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--detections", type=Path, default=None)
    parser.add_argument("--annotated", type=Path, default=None)
    parser.add_argument("--conf-thres", type=float, default=0.25)
    parser.add_argument("--iou-thres", type=float, default=0.45)
    parser.add_argument("--max-detections", type=int, default=100)
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

    outputs = None
    for _ in range(args.warmup):
        outputs = rknn.inference(inputs=[input_tensor])

    latencies_ms: list[float] = []
    output_shapes: list[list[int]] = []
    for _ in range(args.runs):
        t0 = time.perf_counter()
        outputs = rknn.inference(inputs=[input_tensor])
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if outputs and not output_shapes:
            output_shapes = [list(getattr(output, "shape", [])) for output in outputs]

    detections_payload = None
    if args.detections and args.image and outputs:
        try:
            detections_payload, annotated = decode_outputs(
                outputs,
                args.image,
                args.image_size,
                args.conf_thres,
                args.iou_thres,
                args.max_detections,
            )
            args.detections.parent.mkdir(parents=True, exist_ok=True)
            args.detections.write_text(json.dumps(detections_payload, indent=2), encoding="utf-8")
            if args.annotated is not None:
                import cv2

                args.annotated.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(args.annotated), annotated)
        except Exception as exc:
            detections_payload = {"error": str(exc), "detections": []}

    rknn.release()
    total_ms = (time.perf_counter() - started) * 1000.0
    avg_ms = statistics.mean(latencies_ms) if latencies_ms else None
    fps = 1000.0 / avg_ms if avg_ms else None
    output_summary = summarize_yolo_output(outputs) if outputs else None

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
        output_summary=output_summary,
        detections={
            "path": str(args.detections) if args.detections else None,
            "annotated": str(args.annotated) if args.annotated else None,
            "count": len(detections_payload.get("detections", [])) if detections_payload else None,
            "error": detections_payload.get("error") if detections_payload else None,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
