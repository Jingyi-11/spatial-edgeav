#!/usr/bin/env python3
"""Small web dashboard for the Spatial EdgeAV C++ service.

The dashboard does not open the camera. It reads artifacts produced by the
board-local C++ runtime:
  - heartbeat.json
  - events.jsonl
  - latest_frame.jpg
  - edgeav_runtime_frames.json
  - spatial_rules.json
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DEFAULT_RUN_DIR = Path("/home/kickpi/spatial-edgeav/runs/cpp_service")


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spatial EdgeAV Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1117;
      --panel: #121b24;
      --panel-2: #172331;
      --text: #e8eef6;
      --muted: #93a4b7;
      --accent: #38bdf8;
      --good: #34d399;
      --warn: #fbbf24;
      --bad: #fb7185;
      --line: #263546;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      height: 56px;
      padding: 0 20px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #0d141c;
    }
    h1 { font-size: 18px; margin: 0; letter-spacing: 0; }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      color: var(--muted);
      font-size: 13px;
    }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(360px, 0.8fr);
      gap: 16px;
      padding: 16px;
      min-height: calc(100vh - 56px);
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .video-wrap {
      position: relative;
      min-height: 420px;
      background: #020617;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .video-stage {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #020617;
    }
    #stream {
      width: 100%;
      height: auto;
      display: block;
      aspect-ratio: 16 / 9;
      object-fit: contain;
      background: #020617;
    }
    #overlay {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }
    .video-title {
      position: absolute;
      left: 12px;
      top: 12px;
      background: rgb(2 6 23 / 0.72);
      border: 1px solid rgb(148 163 184 / 0.3);
      border-radius: 6px;
      padding: 7px 9px;
      font-size: 13px;
      color: var(--muted);
    }
    .side {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .panel-head {
      height: 42px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px;
      color: var(--muted);
      font-size: 13px;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
    }
    .metric {
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 76px;
    }
    .metric label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .metric strong {
      display: block;
      font-size: 22px;
      line-height: 1.1;
    }
    .ok { color: var(--good); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .events {
      max-height: 440px;
      overflow: auto;
      padding: 8px;
    }
    .event {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 9px;
      margin-bottom: 8px;
    }
    .event-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 13px;
    }
    .event code {
      color: var(--accent);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    .event p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .actions {
      display: flex;
      gap: 8px;
      padding: 12px;
      border-top: 1px solid var(--line);
    }
    button {
      background: #1f8ec7;
      color: white;
      border: 0;
      border-radius: 6px;
      padding: 9px 12px;
      font-size: 13px;
      cursor: pointer;
    }
    button.secondary { background: #243445; }
    .toast {
      position: fixed;
      right: 18px;
      bottom: 18px;
      max-width: 380px;
      background: #172331;
      border: 1px solid var(--accent);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 12px;
      box-shadow: 0 20px 50px rgb(0 0 0 / 0.35);
      opacity: 0;
      transform: translateY(10px);
      transition: 160ms ease;
      pointer-events: none;
    }
    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; }
      .video-wrap { min-height: 260px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Spatial EdgeAV Dashboard</h1>
    <div class="pill" id="clock">connecting</div>
  </header>
  <main>
    <section>
      <div class="video-wrap">
        <div class="video-title">Live camera stream: HTTP MJPEG + spatial overlay</div>
        <div class="video-stage">
          <img id="stream" src="/stream.mjpg" alt="Live camera stream">
          <canvas id="overlay"></canvas>
        </div>
      </div>
    </section>
    <div class="side">
      <section>
        <div class="panel-head">
          <span>Runtime Health</span>
          <span id="status" class="warn">unknown</span>
        </div>
        <div class="metrics">
          <div class="metric"><label>Camera FPS</label><strong id="fps">-</strong></div>
          <div class="metric"><label>End-to-End</label><strong id="latency">-</strong></div>
          <div class="metric"><label>RKNN Frames</label><strong id="rknnFrames">-</strong></div>
          <div class="metric"><label>Events</label><strong id="eventsCount">-</strong></div>
          <div class="metric"><label>RKNN Failures</label><strong id="rknnFailures">-</strong></div>
          <div class="metric"><label>Spatial Failures</label><strong id="spatialFailures">-</strong></div>
        </div>
        <div class="actions">
          <button id="enableAudio">Enable Alert Sound</button>
          <button class="secondary" id="testBeep">Test Beep</button>
        </div>
      </section>
      <section>
        <div class="panel-head">
          <span>Recent Spatial Events</span>
          <span id="eventState">polling</span>
        </div>
        <div class="events" id="events"></div>
      </section>
    </div>
  </main>
  <div class="toast" id="toast"></div>
  <script>
    let audioEnabled = false;
    let lastEventId = localStorage.getItem("edgeav:lastEventId") || "";
    let audioCtx = null;
    let zones = [];
    let detections = [];
    let recentEvents = [];
    let streamShape = { width: 1280, height: 720 };

    function fmt(value, digits = 1) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return Number(value).toFixed(digits);
    }

    function beep() {
      if (!audioEnabled) return;
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.18, audioCtx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.28);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.3);
    }

    function showToast(event) {
      const toast = document.getElementById("toast");
      const obj = event.object || {};
      toast.innerHTML = `<strong>${event.rule_id || "spatial event"}</strong><br>${obj.class_name || "object"} ${obj.confidence ? Number(obj.confidence).toFixed(2) : ""}<br>${event.message || ""}`;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 5500);
    }

    function scalePoint(x, y, canvas) {
      return [x * canvas.width / streamShape.width, y * canvas.height / streamShape.height];
    }

    function drawOverlay() {
      const canvas = document.getElementById("overlay");
      const img = document.getElementById("stream");
      const rect = img.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = Math.max(1, Math.round(rect.width));
      const cssHeight = Math.max(1, Math.round(rect.height));
      const targetWidth = Math.round(cssWidth * dpr);
      const targetHeight = Math.round(cssHeight * dpr);
      if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        canvas.style.width = `${cssWidth}px`;
        canvas.style.height = `${cssHeight}px`;
      }

      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.lineWidth = Math.max(2, 2 * dpr);
      ctx.font = `${Math.max(12, 12 * dpr)}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`;

      for (const zone of zones) {
        const points = zone.polygon_xy || [];
        if (points.length < 3) continue;
        ctx.beginPath();
        points.forEach((pt, idx) => {
          const [x, y] = scalePoint(Number(pt[0]), Number(pt[1]), canvas);
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.closePath();
        ctx.fillStyle = "rgb(56 189 248 / 0.12)";
        ctx.strokeStyle = "rgb(56 189 248 / 0.85)";
        ctx.fill();
        ctx.stroke();

        const [lx, ly] = scalePoint(Number(points[0][0]), Number(points[0][1]), canvas);
        const label = zone.name || zone.id || "zone";
        ctx.fillStyle = "rgb(2 6 23 / 0.72)";
        ctx.fillRect(lx, Math.max(0, ly - 20 * dpr), Math.min(260 * dpr, label.length * 8 * dpr + 18 * dpr), 20 * dpr);
        ctx.fillStyle = "rgb(226 232 240)";
        ctx.fillText(label, lx + 6 * dpr, Math.max(14 * dpr, ly - 6 * dpr));
      }

      for (const det of detections.slice(0, 12)) {
        const box = det.bbox_original_xyxy || det.bbox_xyxy;
        if (!box || box.length !== 4) continue;
        const [x1, y1] = scalePoint(Number(box[0]), Number(box[1]), canvas);
        const [x2, y2] = scalePoint(Number(box[2]), Number(box[3]), canvas);
        const label = `${det.class_name || det.class_id || "obj"} ${det.confidence ? Number(det.confidence).toFixed(2) : ""}`;
        ctx.strokeStyle = "rgb(52 211 153 / 0.95)";
        ctx.fillStyle = "rgb(52 211 153 / 0.16)";
        ctx.lineWidth = Math.max(2, 2 * dpr);
        ctx.strokeRect(x1, y1, Math.max(1, x2 - x1), Math.max(1, y2 - y1));
        ctx.fillRect(x1, Math.max(0, y1 - 20 * dpr), Math.min(220 * dpr, label.length * 8 * dpr + 16 * dpr), 20 * dpr);
        ctx.fillStyle = "#052e1f";
        ctx.fillText(label, x1 + 5 * dpr, Math.max(14 * dpr, y1 - 6 * dpr));
      }

      for (const ev of recentEvents.slice(-8)) {
        const obj = ev.object || {};
        const box = obj.bbox_original_xyxy;
        if (!box || box.length !== 4) continue;
        const [x1, y1] = scalePoint(Number(box[0]), Number(box[1]), canvas);
        const [x2, y2] = scalePoint(Number(box[2]), Number(box[3]), canvas);
        ctx.strokeStyle = "rgb(251 191 36 / 0.98)";
        ctx.lineWidth = Math.max(3, 3 * dpr);
        ctx.strokeRect(x1, y1, Math.max(1, x2 - x1), Math.max(1, y2 - y1));
      }
    }

    async function loadSpatialConfig() {
      try {
        const res = await fetch("/api/spatial-config", { cache: "no-store" });
        const data = await res.json();
        zones = data.zones || [];
        if (data.frame && data.frame.width && data.frame.height) {
          streamShape = data.frame;
        }
        drawOverlay();
      } catch (err) {
        zones = [];
      }
    }

    async function loadDetections() {
      try {
        const res = await fetch("/api/latest-detections", { cache: "no-store" });
        const data = await res.json();
        detections = data.detections || [];
        if (data.frame && data.frame.width && data.frame.height) {
          streamShape = data.frame;
        }
        drawOverlay();
      } catch (err) {
        detections = [];
      }
    }

    async function loadHeartbeat() {
      try {
        const res = await fetch("/api/heartbeat", { cache: "no-store" });
        const data = await res.json();
        const status = data.status || "unknown";
        const statusEl = document.getElementById("status");
        statusEl.textContent = status;
        statusEl.className = status === "running" ? "ok" : status === "stopped" ? "warn" : "bad";
        document.getElementById("fps").textContent = fmt(data.measured_fps, 1);
        document.getElementById("latency").textContent = fmt(data.latency_ms && data.latency_ms.rknn_end_to_end_mean, 1) + " ms";
        document.getElementById("rknnFrames").textContent = data.rknn_continuous ? data.rknn_continuous.frames : "-";
        document.getElementById("eventsCount").textContent = data.spatial ? data.spatial.events : "-";
        document.getElementById("rknnFailures").textContent = data.rknn_continuous ? data.rknn_continuous.failures : "-";
        document.getElementById("spatialFailures").textContent = data.spatial ? data.spatial.failures : "-";
        document.getElementById("clock").textContent = new Date().toLocaleTimeString();
      } catch (err) {
        document.getElementById("status").textContent = "offline";
        document.getElementById("status").className = "bad";
      }
    }

    async function loadEvents() {
      try {
        const res = await fetch("/api/events?limit=20", { cache: "no-store" });
        const events = await res.json();
        renderEvents(events, "polling");
      } catch (err) {
        document.getElementById("eventState").textContent = "error";
      }
    }

    function renderEvents(events, stateLabel = "ok") {
      recentEvents = events;
      const box = document.getElementById("events");
      box.innerHTML = events.slice().reverse().map(ev => {
        const obj = ev.object || {};
        return `<div class="event">
          <div class="event-top"><code>${ev.rule_id || "-"}</code><span>${obj.confidence ? Number(obj.confidence).toFixed(2) : ""}</span></div>
          <p>${ev.message || ""}</p>
          <p>${obj.class_name || "object"} · frame ${ev.frame_index ?? "-"} · object ${obj.object_id ?? "-"}</p>
        </div>`;
      }).join("") || `<div class="event"><p>No events yet.</p></div>`;

      const newest = events.length ? events[events.length - 1] : null;
      if (newest && newest.event_id && newest.event_id !== lastEventId) {
        if (lastEventId) {
          showToast(newest);
          beep();
        }
        lastEventId = newest.event_id;
        localStorage.setItem("edgeav:lastEventId", lastEventId);
      }
      document.getElementById("eventState").textContent = stateLabel;
      drawOverlay();
    }

    function connectEvents() {
      if (!window.EventSource) {
        setInterval(loadEvents, 1000);
        return;
      }
      const source = new EventSource("/events.sse");
      source.addEventListener("events", (msg) => {
        try {
          renderEvents(JSON.parse(msg.data), "sse");
        } catch (err) {
          document.getElementById("eventState").textContent = "parse error";
        }
      });
      source.onerror = () => {
        document.getElementById("eventState").textContent = "reconnecting";
      };
    }

    document.getElementById("enableAudio").addEventListener("click", () => {
      audioEnabled = true;
      beep();
      document.getElementById("enableAudio").textContent = "Alert Sound Enabled";
    });
    document.getElementById("testBeep").addEventListener("click", () => {
      audioEnabled = true;
      beep();
    });

    loadHeartbeat();
    loadSpatialConfig();
    loadDetections();
    loadEvents();
    connectEvents();
    setInterval(loadHeartbeat, 1000);
    setInterval(loadDetections, 700);
    window.addEventListener("resize", drawOverlay);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SpatialEdgeAVDashboard/0.1"

    @property
    def run_dir(self) -> Path:
        return self.server.run_dir  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        if self.server.quiet:  # type: ignore[attr-defined]
            return
        super().log_message(fmt, *args)

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(data, "application/json; charset=utf-8", status)

    def read_json(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_frame_path(self) -> Path:
        heartbeat_path = self.run_dir / "heartbeat.json"
        try:
            heartbeat = self.read_json(heartbeat_path)
            latest = heartbeat.get("latest_jpeg", {}).get("dump_path")  # type: ignore[union-attr]
            if latest:
                return Path(str(latest))
        except Exception:
            pass
        return self.run_dir / "latest_frame.jpg"

    def events_path(self) -> Path:
        heartbeat_path = self.run_dir / "heartbeat.json"
        try:
            heartbeat = self.read_json(heartbeat_path)
            events = heartbeat.get("spatial", {}).get("events_jsonl")  # type: ignore[union-attr]
            if events:
                return Path(str(events))
        except Exception:
            pass
        return self.run_dir / "events.jsonl"

    def frames_path(self) -> Path:
        heartbeat_path = self.run_dir / "heartbeat.json"
        try:
            heartbeat = self.read_json(heartbeat_path)
            frames = heartbeat.get("frames_json")  # type: ignore[union-attr]
            if frames:
                return Path(str(frames))
        except Exception:
            pass
        return self.run_dir / "edgeav_runtime_frames.json"

    def spatial_rules_path(self) -> Path | None:
        heartbeat_path = self.run_dir / "heartbeat.json"
        try:
            heartbeat = self.read_json(heartbeat_path)
            rules = heartbeat.get("spatial", {}).get("rules")  # type: ignore[union-attr]
            if rules:
                return Path(str(rules))
        except Exception:
            pass
        default_path = Path("/home/kickpi/spatial-edgeav/configs/spatial_rules.json")
        return default_path if default_path.exists() else None

    def frame_shape(self) -> dict[str, int]:
        heartbeat_path = self.run_dir / "heartbeat.json"
        try:
            heartbeat = self.read_json(heartbeat_path)
            camera = heartbeat.get("camera", {})  # type: ignore[union-attr]
            return {
                "width": int(camera.get("width", 1280)),
                "height": int(camera.get("height", 720)),
            }
        except Exception:
            return {"width": 1280, "height": 720}

    def read_events(self, limit: int) -> list[dict[str, object]]:
        path = self.events_path()
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        events: list[dict[str, object]] = []
        for line in lines[-max(1, min(limit, 200)):]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return events

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif parsed.path == "/api/heartbeat":
            self.handle_heartbeat()
        elif parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["20"])[0])
            self.handle_events(limit)
        elif parsed.path == "/api/spatial-config":
            self.handle_spatial_config()
        elif parsed.path == "/api/latest-detections":
            self.handle_latest_detections()
        elif parsed.path == "/events.sse":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["20"])[0])
            self.handle_events_sse(limit)
        elif parsed.path == "/snapshot.jpg":
            self.handle_snapshot()
        elif parsed.path == "/stream.mjpg":
            self.handle_stream()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def handle_heartbeat(self) -> None:
        path = self.run_dir / "heartbeat.json"
        if not path.exists():
            self.send_json({"status": "missing", "error": f"{path} not found"}, 404)
            return
        try:
            self.send_json(self.read_json(path))
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 500)

    def handle_events(self, limit: int) -> None:
        self.send_json(self.read_events(limit))

    def handle_spatial_config(self) -> None:
        path = self.spatial_rules_path()
        if not path or not path.exists():
            self.send_json({"frame": self.frame_shape(), "zones": [], "rules": []})
            return
        try:
            config = self.read_json(path)
            frame = self.frame_shape()
            zones = []
            for zone in config.get("zones", []):  # type: ignore[union-attr]
                polygon_norm = zone.get("polygon_norm", [])
                polygon_xy = [
                    [float(x) * frame["width"], float(y) * frame["height"]]
                    for x, y in polygon_norm
                ]
                zones.append({
                    "id": zone.get("id"),
                    "name": zone.get("name", zone.get("id")),
                    "polygon_norm": polygon_norm,
                    "polygon_xy": polygon_xy,
                })
            self.send_json({"frame": frame, "zones": zones, "rules": config.get("rules", [])})  # type: ignore[union-attr]
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 500)

    def handle_latest_detections(self) -> None:
        path = self.frames_path()
        if not path.exists():
            self.send_json({"frame": self.frame_shape(), "detections": []})
            return
        try:
            frames = self.read_json(path)
            if not isinstance(frames, list) or not frames:
                self.send_json({"frame": self.frame_shape(), "detections": []})
                return
            latest = frames[-1]
            self.send_json({
                "frame": self.frame_shape(),
                "sequence": latest.get("sequence"),
                "ts_ms": latest.get("ts_ms"),
                "detections": latest.get("detections", []),
            })
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 500)

    def handle_events_sse(self, limit: int) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_payload = ""
        while True:
            try:
                payload = json.dumps(self.read_events(limit), ensure_ascii=False)
                if payload != last_payload:
                    self.wfile.write(b"event: events\n")
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_payload = payload
                else:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                time.sleep(1.0)
            except (BrokenPipeError, ConnectionResetError):
                return

    def handle_snapshot(self) -> None:
        path = self.latest_frame_path()
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "latest frame not found")
            return
        self.send_bytes(path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/jpeg")

    def handle_stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=edgeav")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        last_token: tuple[int, int] | None = None
        while True:
            try:
                path = self.latest_frame_path()
                stat = path.stat()
                token = (stat.st_mtime_ns, stat.st_size)
                if token != last_token and stat.st_size > 0:
                    frame = path.read_bytes()
                    self.wfile.write(b"--edgeav\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                    last_token = token
                time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return
            except FileNotFoundError:
                time.sleep(0.2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("EDGEAV_DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("EDGEAV_DASHBOARD_PORT", "8080")))
    parser.add_argument("--run-dir", type=Path, default=Path(os.environ.get("EDGEAV_RUN_DIR", DEFAULT_RUN_DIR)))
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.run_dir = args.run_dir  # type: ignore[attr-defined]
    server.quiet = args.quiet  # type: ignore[attr-defined]
    print(f"Spatial EdgeAV dashboard: http://{args.host}:{args.port}")
    print(f"Run dir: {args.run_dir}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
