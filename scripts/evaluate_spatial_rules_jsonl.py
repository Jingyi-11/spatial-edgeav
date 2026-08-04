#!/usr/bin/env python3
"""Evaluate spatial rules over continuous camera frame detections."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from evaluate_spatial_rules import evaluate, read_json


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def frame_to_detections_payload(frame: dict[str, Any], report: dict[str, Any], source: str) -> dict[str, Any]:
    camera = report.get("camera", {})
    return {
        "source": source,
        "image": {
            "width": int(camera.get("width", 0)),
            "height": int(camera.get("height", 0)),
        },
        "detections": frame.get("detections", []),
    }


def summarize_events(events: list[dict[str, Any]], observations_count: int) -> dict[str, Any]:
    by_rule: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for event in events:
        by_rule[event["rule_id"]] = by_rule.get(event["rule_id"], 0) + 1
        cls = str(event.get("object", {}).get("class_name", "unknown"))
        by_class[cls] = by_class.get(cls, 0) + 1
    return {
        "observations": observations_count,
        "events": len(events),
        "by_rule": by_rule,
        "by_class": by_class,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--rules", default=Path("configs/spatial_rules.json"), type=Path)
    parser.add_argument("--observations-jsonl", required=True, type=Path)
    parser.add_argument("--events-jsonl", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    frames_payload = read_json(args.frames)
    report = read_json(args.report)
    config = read_json(args.rules)
    base_ts_ms = int(time.time() * 1000)
    frame_interval_ms = round(1000.0 / float(report.get("camera", {}).get("fps", 30)))

    observations: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    source = str(args.frames)
    for frame in frames_payload.get("frames", []):
        frame_index = int(frame.get("index", len(observations)))
        ts_ms = base_ts_ms + frame_index * frame_interval_ms
        detections = frame_to_detections_payload(frame, report, source)
        observation, frame_events = evaluate(detections, config, ts_ms)
        observation["frame_index"] = frame_index
        observation["latency_ms"] = frame.get("latency_ms")
        observations.append(observation)
        for event_idx, event in enumerate(frame_events):
            event["frame_index"] = frame_index
            event["event_id"] = f"{frame_index}:{event_idx}:{event['rule_id']}"
            events.append(event)

    summary = summarize_events(events, len(observations))
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_jsonl(args.observations_jsonl, observations)
    write_jsonl(args.events_jsonl, events)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
