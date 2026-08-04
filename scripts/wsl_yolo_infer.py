#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: wsl_yolo_infer.py <input.jpg> <annotated.jpg> "
            "<detections.json> <inference.json>",
            file=sys.stderr,
        )
        return 2

    image_path = Path(sys.argv[1])
    annotated_path = Path(sys.argv[2])
    detections_path = Path(sys.argv[3])
    inference_path = Path(sys.argv[4])

    start = time.perf_counter()
    model = YOLO("yolov8n.pt")
    load_done = time.perf_counter()
    result = model(str(image_path), imgsz=640, device="cpu", verbose=False)[0]
    infer_done = time.perf_counter()

    annotated = result.plot()
    cv2.imwrite(str(annotated_path), annotated)

    names = result.names
    boxes = result.boxes
    detections = []
    if boxes is not None:
        xyxy = boxes.xyxy.cpu().tolist()
        conf = boxes.conf.cpu().tolist()
        cls = boxes.cls.cpu().tolist()
        for idx, (box, score, class_id) in enumerate(zip(xyxy, conf, cls)):
            x1, y1, x2, y2 = box
            detections.append(
                {
                    "id": idx,
                    "class_id": int(class_id),
                    "class_name": names[int(class_id)],
                    "confidence": round(float(score), 4),
                    "bbox_xyxy": [round(float(v), 2) for v in [x1, y1, x2, y2]],
                    "bbox_xywh": [
                        round(float(x1), 2),
                        round(float(y1), 2),
                        round(float(x2 - x1), 2),
                        round(float(y2 - y1), 2),
                    ],
                }
            )

    image = cv2.imread(str(image_path))
    height, width = image.shape[:2] if image is not None else (None, None)
    detections_payload = {
        "source": str(image_path),
        "image": {"width": width, "height": height},
        "model": "yolov8n.pt",
        "device": "cpu",
        "detections": detections,
    }
    detections_path.write_text(
        json.dumps(detections_payload, indent=2), encoding="utf-8"
    )

    speed = getattr(result, "speed", {}) or {}
    inference_payload = {
        "python_ms": {
            "model_load": round((load_done - start) * 1000, 3),
            "predict_total": round((infer_done - load_done) * 1000, 3),
        },
        "ultralytics_ms": {
            "preprocess": round(float(speed.get("preprocess", 0.0)), 3),
            "inference": round(float(speed.get("inference", 0.0)), 3),
            "postprocess": round(float(speed.get("postprocess", 0.0)), 3),
        },
        "environment": {
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
        },
    }
    inference_path.write_text(
        json.dumps(inference_payload, indent=2), encoding="utf-8"
    )

    print(json.dumps({"detections": len(detections), **inference_payload}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
