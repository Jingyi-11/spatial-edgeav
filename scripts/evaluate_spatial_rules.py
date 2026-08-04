#!/usr/bin/env python3
"""Evaluate spatial zone rules on YOLO detections."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


BBox = tuple[float, float, float, float]
Point = tuple[float, float]


def now_ms() -> int:
    return int(time.time() * 1000)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def denormalize_polygon(points: list[list[float]], width: int, height: int) -> list[Point]:
    return [(float(x) * width, float(y) * height) for x, y in points]


def polygon_bounds(poly: list[Point]) -> BBox:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def boxes_intersect(a: BBox, b: BBox) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 < bx1 or ax1 > bx2 or ay2 < by1 or ay1 > by2)


def detection_box(det: dict[str, Any]) -> BBox:
    x1, y1, x2, y2 = det["bbox_xyxy"]
    return float(x1), float(y1), float(x2), float(y2)


def build_observation(detections: dict[str, Any], zones: list[dict[str, Any]], ts_ms: int) -> dict[str, Any]:
    image = detections.get("image", {})
    return {
        "ts_ms": ts_ms,
        "source": detections.get("source"),
        "width": image.get("width"),
        "height": image.get("height"),
        "objects": [
            {
                "object_id": det.get("id"),
                "class_id": det.get("class_id"),
                "class_name": det.get("class_name"),
                "confidence": det.get("confidence"),
                "bbox_xyxy": det.get("bbox_xyxy"),
                "bbox_xywh": det.get("bbox_xywh"),
            }
            for det in detections.get("detections", [])
        ],
        "zones": zones,
    }


def evaluate(detections: dict[str, Any], config: dict[str, Any], ts_ms: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    image = detections.get("image", {})
    width = int(image["width"])
    height = int(image["height"])

    zones_by_id: dict[str, dict[str, Any]] = {}
    for zone in config.get("zones", []):
        polygon = denormalize_polygon(zone["polygon_norm"], width, height)
        zones_by_id[zone["id"]] = {
            **zone,
            "polygon_xy": [[round(x, 2), round(y, 2)] for x, y in polygon],
            "bounds_xyxy": [round(v, 2) for v in polygon_bounds(polygon)],
        }

    events: list[dict[str, Any]] = []
    for rule in config.get("rules", []):
        if rule.get("type") != "zone_intersection":
            continue
        zone = zones_by_id.get(rule.get("zone_id"))
        if not zone:
            continue
        zone_box = tuple(float(v) for v in zone["bounds_xyxy"])
        for det in detections.get("detections", []):
            if det.get("class_name") != rule.get("class_name"):
                continue
            if float(det.get("confidence", 0.0)) < float(rule.get("min_confidence", 0.0)):
                continue
            if not boxes_intersect(detection_box(det), zone_box):
                continue
            events.append(
                {
                    "ts_ms": ts_ms,
                    "type": "spatial_rule_triggered",
                    "rule_id": rule["id"],
                    "severity": rule.get("severity", "info"),
                    "message": rule.get("message", ""),
                    "zone_id": zone["id"],
                    "zone_name": zone.get("name", zone["id"]),
                    "relation": "intersects",
                    "object": {
                        "object_id": det.get("id"),
                        "class_name": det.get("class_name"),
                        "confidence": det.get("confidence"),
                        "bbox_xyxy": det.get("bbox_xyxy"),
                        "bbox_xywh": det.get("bbox_xywh"),
                    },
                }
            )

    observation = build_observation(detections, list(zones_by_id.values()), ts_ms)
    return observation, events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detections", required=True, type=Path)
    parser.add_argument("--rules", default=Path("configs/spatial_rules.json"), type=Path)
    parser.add_argument("--observation-out", required=True, type=Path)
    parser.add_argument("--events-out", required=True, type=Path)
    args = parser.parse_args()

    ts_ms = now_ms()
    observation, events = evaluate(read_json(args.detections), read_json(args.rules), ts_ms)
    write_json(args.observation_out, observation)
    write_json(args.events_out, {"ts_ms": ts_ms, "events": events})
    print(json.dumps({"objects": len(observation["objects"]), "events": len(events)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
