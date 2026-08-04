#!/usr/bin/env python3
"""Continuous RK3576 USB-camera capture plus RKNN YOLO inference baseline."""

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

from rk3576_rknn_smoke_test import (
    COCO80,
    box_iou,
    box_process,
    flatten_hw_channels,
    group_rockchip_yolov8_outputs,
    module_status,
    nms,
    percentile,
)


def annotate(image_bgr: Any, detections: list[dict[str, Any]]) -> Any:
    import cv2

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
    return annotated


def decode_raw_yolov8(
    outputs: list[Any],
    image_bgr: Any,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
    max_detections: int,
) -> list[dict[str, Any]]:
    import numpy as np

    height, width = image_bgr.shape[:2]
    pred = np.squeeze(np.asarray(outputs[0]))
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
    kept = nms(detections, iou_threshold)[:max_detections]
    for idx, det in enumerate(kept):
        det["id"] = idx
    return kept


def decode_rockchip_yolov8(
    outputs: list[Any],
    image_bgr: Any,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
    max_detections: int,
) -> list[dict[str, Any]]:
    import numpy as np

    groups = group_rockchip_yolov8_outputs(outputs)
    if not groups:
        raise ValueError("no Rockchip YOLOv8 output groups found")

    height, width = image_bgr.shape[:2]
    box_arrays = []
    score_arrays = []
    for box_tensor, score_tensor, _score_sum in groups:
        box_arrays.append(flatten_hw_channels(box_process(box_tensor, image_size)))
        score_arrays.append(flatten_hw_channels(score_tensor))

    boxes = np.concatenate(box_arrays, axis=0)
    scores = np.concatenate(score_arrays, axis=0)
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

    kept = nms(detections, iou_threshold)[:max_detections]
    for idx, det in enumerate(kept):
        det["id"] = idx
    return kept


def decode_outputs(
    outputs: list[Any],
    image_bgr: Any,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
    max_detections: int,
) -> tuple[str, list[dict[str, Any]]]:
    import numpy as np

    if group_rockchip_yolov8_outputs(outputs):
        return (
            "rockchip_yolov8_optimized_head",
            decode_rockchip_yolov8(outputs, image_bgr, image_size, conf_threshold, iou_threshold, max_detections),
        )
    pred = np.squeeze(np.asarray(outputs[0]))
    if pred.shape[0] == 84 or pred.shape[-1] == 84:
        return (
            "yolov8_raw_head",
            decode_raw_yolov8(outputs, image_bgr, image_size, conf_threshold, iou_threshold, max_detections),
        )
    raise ValueError(f"unsupported output shapes: {[list(np.asarray(output).shape) for output in outputs]}")


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


def finish(report: dict[str, Any], report_path: Path, status: str, exit_code: int = 0, **extra: Any) -> int:
    report["status"] = status
    report.update(extra)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--device", default="/dev/video73")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--conf-thres", type=float, default=0.25)
    parser.add_argument("--iou-thres", type=float, default=0.45)
    parser.add_argument("--max-detections", type=int, default=100)
    parser.add_argument("--report", type=Path, default=Path("rk3576_rknn_camera_report.json"))
    parser.add_argument("--frames-json", type=Path, default=None)
    parser.add_argument("--annotated", type=Path, default=None)
    args = parser.parse_args()

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
        "camera": {
            "device": args.device,
            "width": args.width,
            "height": args.height,
            "fps": args.fps,
        },
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

    if not args.model.exists():
        return finish(report, args.report, "missing_model", 2)
    if not Path(args.device).exists():
        return finish(report, args.report, "missing_camera_device", 3)
    if not report["modules"]["cv2"]["available"] or not report["modules"]["numpy"]["available"]:
        return finish(report, args.report, "missing_image_dependency", 4)
    if not report["modules"]["rknnlite"]["available"]:
        return finish(report, args.report, "missing_rknn_lite", 5)

    import cv2
    import numpy as np
    from rknnlite.api import RKNNLite

    rknn = RKNNLite(verbose=False)
    ret = rknn.load_rknn(str(args.model))
    if ret != 0:
        rknn.release()
        return finish(report, args.report, "load_rknn_failed", 6, rknn_ret=ret)
    ret = rknn.init_runtime()
    if ret != 0:
        rknn.release()
        return finish(report, args.report, "init_runtime_failed", 7, rknn_ret=ret)

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if not cap.isOpened():
        rknn.release()
        return finish(report, args.report, "open_camera_failed", 8)

    frames: list[dict[str, Any]] = []
    capture_ms: list[float] = []
    preprocess_ms: list[float] = []
    inference_ms: list[float] = []
    postprocess_ms: list[float] = []
    end_to_end_ms: list[float] = []
    detections_by_class: dict[str, int] = {}
    postprocess_type = None
    last_annotated = None
    started = time.perf_counter()

    processed = 0
    for frame_idx in range(args.frames + args.warmup):
        frame_start = time.perf_counter()
        t0 = time.perf_counter()
        ok, frame_bgr = cap.read()
        t1 = time.perf_counter()
        if not ok or frame_bgr is None:
            if frame_idx < args.warmup:
                continue
            frames.append({"index": frame_idx - args.warmup, "error": "capture_failed"})
            continue

        t2 = time.perf_counter()
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (args.image_size, args.image_size), interpolation=cv2.INTER_LINEAR)
        input_tensor = np.expand_dims(resized, axis=0)
        t3 = time.perf_counter()

        outputs = rknn.inference(inputs=[input_tensor])
        t4 = time.perf_counter()

        if frame_idx < args.warmup:
            continue

        try:
            postprocess_type, detections = decode_outputs(
                outputs,
                frame_bgr,
                args.image_size,
                args.conf_thres,
                args.iou_thres,
                args.max_detections,
            )
            error = None
        except Exception as exc:
            detections = []
            error = str(exc)
        t5 = time.perf_counter()

        for det in detections:
            name = str(det.get("class_name", det.get("class_id", "unknown")))
            detections_by_class[name] = detections_by_class.get(name, 0) + 1

        last_annotated = annotate(frame_bgr, detections)
        capture_ms.append((t1 - t0) * 1000.0)
        preprocess_ms.append((t3 - t2) * 1000.0)
        inference_ms.append((t4 - t3) * 1000.0)
        postprocess_ms.append((t5 - t4) * 1000.0)
        end_to_end_ms.append((t5 - frame_start) * 1000.0)
        frames.append(
            {
                "index": processed,
                "detections_count": len(detections),
                "detections": detections[:5],
                "latency_ms": {
                    "capture": round(capture_ms[-1], 3),
                    "preprocess": round(preprocess_ms[-1], 3),
                    "inference": round(inference_ms[-1], 3),
                    "postprocess": round(postprocess_ms[-1], 3),
                    "end_to_end": round(end_to_end_ms[-1], 3),
                },
                "error": error,
            }
        )
        processed += 1

    cap.release()
    rknn.release()
    total_ms = (time.perf_counter() - started) * 1000.0

    if args.frames_json is not None:
        args.frames_json.parent.mkdir(parents=True, exist_ok=True)
        args.frames_json.write_text(json.dumps({"frames": frames}, indent=2), encoding="utf-8")

    if args.annotated is not None and last_annotated is not None:
        args.annotated.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(args.annotated), last_annotated)

    end_to_end_mean = statistics.mean(end_to_end_ms) if end_to_end_ms else None
    inference_mean = statistics.mean(inference_ms) if inference_ms else None
    return finish(
        report,
        args.report,
        "ok",
        frames_requested=args.frames,
        frames_processed=processed,
        warmup=args.warmup,
        postprocess={
            "type": postprocess_type,
            "confidence_threshold": args.conf_thres,
            "iou_threshold": args.iou_thres,
            "max_detections": args.max_detections,
        },
        latency_ms={
            "capture": summarize(capture_ms),
            "preprocess": summarize(preprocess_ms),
            "inference": summarize(inference_ms),
            "postprocess": summarize(postprocess_ms),
            "end_to_end": summarize(end_to_end_ms),
        },
        fps={
            "inference_only": round(1000.0 / inference_mean, 3) if inference_mean else None,
            "end_to_end": round(1000.0 / end_to_end_mean, 3) if end_to_end_mean else None,
        },
        total_elapsed_ms=round(total_ms, 3),
        detections={
            "by_class": detections_by_class,
            "frames_with_detections": sum(1 for frame in frames if frame.get("detections_count", 0) > 0),
            "frames_json": str(args.frames_json) if args.frames_json else None,
            "annotated": str(args.annotated) if args.annotated else None,
            "last_frame_top": frames[-1].get("detections", []) if frames else [],
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
