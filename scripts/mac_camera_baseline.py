#!/usr/bin/env python3
"""MacBook USB-camera baseline for Spatial EdgeAV.

This baseline validates the non-model parts of the project:
camera capture, spatial zone rules, event logging, and snapshots.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import cv2
except ImportError as exc:  # pragma: no cover - user environment guard
    raise SystemExit(
        "OpenCV is not installed. Run: python3 -m pip install -r requirements-mac.txt"
    ) from exc

try:
    import yaml
except ImportError as exc:  # pragma: no cover - user environment guard
    raise SystemExit("PyYAML is not installed. Run: python3 -m pip install PyYAML") from exc


Point = Tuple[int, int]


@dataclass
class TrackState:
    inside_since_ms: int | None = None
    last_event_ms: int = 0


def now_ms() -> int:
    return int(time.time() * 1000)


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return yaml.safe_load(fp)


def normalized_polygon(points: List[List[float]], width: int, height: int) -> List[Point]:
    return [(int(x * width), int(y * height)) for x, y in points]


def rect_intersects_poly(rect: Tuple[int, int, int, int], polygon: List[Point]) -> bool:
    x, y, w, h = rect
    mask_rect = (x, y, x + w, y + h)
    px_min = min(p[0] for p in polygon)
    px_max = max(p[0] for p in polygon)
    py_min = min(p[1] for p in polygon)
    py_max = max(p[1] for p in polygon)
    return not (
        mask_rect[2] < px_min
        or mask_rect[0] > px_max
        or mask_rect[3] < py_min
        or mask_rect[1] > py_max
    )


def ensure_output(run_dir: Path) -> Tuple[Path, Path]:
    snapshots = run_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    events = run_dir / "events.jsonl"
    return events, snapshots


def write_event(events_path: Path, payload: Dict[str, Any]) -> None:
    with events_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def draw_ui(
    frame: Any,
    polygon: List[Point],
    boxes: List[Tuple[int, int, int, int]],
    active: bool,
    fps: float,
) -> None:
    import numpy as np

    pts = np.array(polygon, dtype=np.int32)
    cv2.polylines(frame, [pts], True, (0, 0, 255) if active else (0, 200, 255), 2)
    for x, y, w, h in boxes:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (40, 220, 40), 2)
    status = "EVENT: restricted zone" if active else "monitoring"
    cv2.putText(frame, status, (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, f"fps={fps:.1f}", (18, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def open_camera(index: int, width: int, height: int, fps: int) -> Any:
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera index {index}. Try --camera 1 or another index.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/mac_baseline.yaml")
    parser.add_argument("--camera", type=int, default=None)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    camera_cfg = config["camera"]
    detector_cfg = config["detector"]
    spatial_cfg = config["spatial"]
    actions_cfg = config["actions"]
    output_cfg = config["output"]

    camera_index = args.camera if args.camera is not None else int(camera_cfg["index"])
    cap = open_camera(
        camera_index,
        int(camera_cfg["width"]),
        int(camera_cfg["height"]),
        int(camera_cfg["fps"]),
    )

    subtractor = cv2.createBackgroundSubtractorMOG2(
        history=int(detector_cfg["history"]),
        varThreshold=float(detector_cfg["var_threshold"]),
        detectShadows=True,
    )

    run_dir = Path(output_cfg["run_dir"])
    events_path, snapshots_dir = ensure_output(run_dir)
    state = TrackState()
    frame_count = 0
    fps = 0.0
    fps_t0 = time.time()

    print(f"camera_index={camera_index}")
    print(f"events={events_path}")
    print("press q to quit")

    while True:
        ok, frame = cap.read()
        if not ok:
            print("camera frame read failed")
            break

        height, width = frame.shape[:2]
        polygon = normalized_polygon(spatial_cfg["restricted_zone"], width, height)
        mask = subtractor.apply(frame, learningRate=float(detector_cfg["learning_rate"]))
        _, mask = cv2.threshold(mask, 240, 255, cv2.THRESH_BINARY)
        mask = cv2.medianBlur(mask, 5)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes: List[Tuple[int, int, int, int]] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < float(detector_cfg["min_area"]):
                continue
            boxes.append(cv2.boundingRect(contour))

        inside = any(rect_intersects_poly(box, polygon) for box in boxes)
        t_ms = now_ms()
        active = False
        if inside:
            if state.inside_since_ms is None:
                state.inside_since_ms = t_ms
            dwell_ms = t_ms - state.inside_since_ms
            active = dwell_ms >= int(spatial_cfg["min_dwell_ms"])
        else:
            state.inside_since_ms = None
            dwell_ms = 0

        cooldown_ms = int(actions_cfg["cooldown_ms"])
        if active and t_ms - state.last_event_ms >= cooldown_ms:
            state.last_event_ms = t_ms
            event = {
                "ts_ms": t_ms,
                "type": "restricted_zone_motion",
                "zone": spatial_cfg["zone_name"],
                "camera_index": camera_index,
                "boxes": [{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in boxes],
                "dwell_ms": dwell_ms,
            }
            if actions_cfg.get("snapshot_on_event", True):
                snapshot = snapshots_dir / f"event_{t_ms}.jpg"
                cv2.imwrite(str(snapshot), frame)
                event["snapshot"] = str(snapshot)
            write_event(events_path, event)
            print(json.dumps(event, ensure_ascii=False))

        frame_count += 1
        elapsed = time.time() - fps_t0
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            fps_t0 = time.time()

        if output_cfg.get("show_window", True):
            draw_ui(frame, polygon, boxes, active, fps)
            cv2.imshow("Spatial EdgeAV Mac Baseline", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
