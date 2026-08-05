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
import math
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
    button:disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
    .editor {
      padding: 10px;
      display: grid;
      gap: 10px;
    }
    .editor-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 8px;
      align-items: center;
    }
    select {
      width: 100%;
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      font-size: 13px;
    }
    .hint {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .zones-list {
      max-height: 260px;
      overflow: auto;
      padding: 8px;
    }
    .zone-item {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 9px;
      margin-bottom: 8px;
    }
    .zone-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 13px;
    }
    .zone-item p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }
    .zone-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 999px;
      margin-right: 6px;
      background: var(--muted);
    }
    .zone-dot.active { background: var(--good); }
    .zone-dot.alert { background: var(--warn); }
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
          <span>Zone Editor</span>
          <span id="editorState">view</span>
        </div>
        <div class="editor">
          <div class="editor-row">
            <select id="zoneSelect" aria-label="Select zone"></select>
            <button class="secondary" id="toggleEdit">Edit</button>
            <button id="saveZones" disabled>Save</button>
          </div>
          <div class="hint" id="editorHint">Select a zone and enter Edit mode. Drag polygon points on the video to recalibrate after moving the camera.</div>
        </div>
      </section>
      <section>
        <div class="panel-head">
          <span>Zone Monitor</span>
          <span id="zoneState">live</span>
        </div>
        <div class="zones-list" id="zonesList"></div>
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
    let zoneStatuses = {};
    let detections = [];
    let recentEvents = [];
    let latestSequence = null;
    let streamShape = { width: 1280, height: 720 };
    let editMode = false;
    let selectedZoneId = "";
    let draggingVertex = null;
    let dirtyZones = false;
    const EVENT_HIGHLIGHT_FRAME_TTL = 90;

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

    function unscalePoint(x, y, canvas) {
      return [x * streamShape.width / canvas.width, y * streamShape.height / canvas.height];
    }

    function clamp01(value) {
      return Math.max(0, Math.min(1, value));
    }

    function eventToCanvasPoint(ev) {
      const canvas = document.getElementById("overlay");
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      return [(ev.clientX - rect.left) * dpr, (ev.clientY - rect.top) * dpr];
    }

    function selectedZone() {
      return zones.find(zone => zone.id === selectedZoneId) || zones[0] || null;
    }

    function zoneColor(zone) {
      const state = zoneStatuses[zone.id]?.state || "idle";
      if (editMode && zone.id === selectedZoneId) {
        return { fill: "rgb(251 191 36 / 0.16)", stroke: "rgb(251 191 36 / 0.98)", label: "rgb(2 6 23 / 0.82)" };
      }
      if (state === "alert") return { fill: "rgb(251 191 36 / 0.16)", stroke: "rgb(251 191 36 / 0.95)", label: "rgb(2 6 23 / 0.72)" };
      if (state === "active") return { fill: "rgb(52 211 153 / 0.12)", stroke: "rgb(52 211 153 / 0.9)", label: "rgb(2 6 23 / 0.72)" };
      return { fill: "rgb(56 189 248 / 0.12)", stroke: "rgb(56 189 248 / 0.85)", label: "rgb(2 6 23 / 0.72)" };
    }

    function updateZoneSelector() {
      const select = document.getElementById("zoneSelect");
      const previous = selectedZoneId;
      select.innerHTML = zones.map(zone => `<option value="${zone.id}">${zone.name || zone.id}</option>`).join("");
      selectedZoneId = zones.some(zone => zone.id === previous) ? previous : (zones[0]?.id || "");
      select.value = selectedZoneId;
      document.getElementById("saveZones").disabled = !dirtyZones;
    }

    function renderZoneMonitor() {
      const box = document.getElementById("zonesList");
      box.innerHTML = zones.map(zone => {
        const status = zoneStatuses[zone.id] || { state: "idle", object_count: 0, objects: [] };
        const objects = (status.objects || []).map(obj => `${obj.class_name || "object"} ${obj.confidence ? Number(obj.confidence).toFixed(2) : ""}`).join(", ");
        const state = status.state || "idle";
        const className = state === "alert" ? "alert" : state === "active" ? "active" : "";
        return `<div class="zone-item">
          <div class="zone-top"><span><span class="zone-dot ${className}"></span>${zone.name || zone.id}</span><strong>${status.object_count || 0}</strong></div>
          <p>${state}${objects ? " · " + objects : ""}</p>
        </div>`;
      }).join("") || `<div class="zone-item"><p>No zones configured.</p></div>`;
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
        const colors = zoneColor(zone);
        ctx.beginPath();
        points.forEach((pt, idx) => {
          const [x, y] = scalePoint(Number(pt[0]), Number(pt[1]), canvas);
          if (idx === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.closePath();
        ctx.fillStyle = colors.fill;
        ctx.strokeStyle = colors.stroke;
        ctx.fill();
        ctx.stroke();

        const [lx, ly] = scalePoint(Number(points[0][0]), Number(points[0][1]), canvas);
        const status = zoneStatuses[zone.id];
        const label = `${zone.name || zone.id || "zone"}${status && status.object_count ? " · " + status.object_count : ""}`;
        ctx.fillStyle = colors.label;
        ctx.fillRect(lx, Math.max(0, ly - 20 * dpr), Math.min(260 * dpr, label.length * 8 * dpr + 18 * dpr), 20 * dpr);
        ctx.fillStyle = "rgb(226 232 240)";
        ctx.fillText(label, lx + 6 * dpr, Math.max(14 * dpr, ly - 6 * dpr));

        if (editMode && zone.id === selectedZoneId) {
          for (let idx = 0; idx < points.length; idx += 1) {
            const [vx, vy] = scalePoint(Number(points[idx][0]), Number(points[idx][1]), canvas);
            ctx.beginPath();
            ctx.arc(vx, vy, Math.max(6, 6 * dpr), 0, Math.PI * 2);
            ctx.fillStyle = "rgb(251 191 36)";
            ctx.fill();
            ctx.strokeStyle = "rgb(2 6 23)";
            ctx.lineWidth = Math.max(2, 2 * dpr);
            ctx.stroke();
          }
        }
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
        if (latestSequence !== null && ev.frame_index !== undefined) {
          const ageFrames = Number(latestSequence) - Number(ev.frame_index);
          if (ageFrames < 0 || ageFrames > EVENT_HIGHLIGHT_FRAME_TTL) continue;
        }
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
        if (!dirtyZones) {
          zones = data.zones || [];
          updateZoneSelector();
        }
        if (data.frame && data.frame.width && data.frame.height) {
          streamShape = data.frame;
        }
        drawOverlay();
      } catch (err) {
        zones = [];
      }
    }

    async function loadZoneStatus() {
      try {
        const res = await fetch("/api/zone-status", { cache: "no-store" });
        const data = await res.json();
        zoneStatuses = {};
        for (const zone of data.zones || []) {
          zoneStatuses[zone.id] = zone;
        }
        document.getElementById("zoneState").textContent = "live";
        renderZoneMonitor();
        drawOverlay();
      } catch (err) {
        document.getElementById("zoneState").textContent = "error";
      }
    }

    async function saveZones() {
      const payloadZones = zones.map(zone => ({
        id: zone.id,
        name: zone.name || zone.id,
        polygon_norm: (zone.polygon_xy || []).map(pt => [
          Number((Number(pt[0]) / streamShape.width).toFixed(6)),
          Number((Number(pt[1]) / streamShape.height).toFixed(6)),
        ]),
      }));
      const res = await fetch("/api/spatial-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ zones: payloadZones }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "save failed");
      }
      zones = data.zones || zones;
      dirtyZones = false;
      updateZoneSelector();
      document.getElementById("editorState").textContent = "saved";
      document.getElementById("editorHint").textContent = "Saved. Restart spatial-edgeav-cpp.service for the C++ rule engine to use the new zones; the overlay updates immediately.";
      drawOverlay();
    }

    async function loadDetections() {
      try {
        const res = await fetch("/api/latest-detections", { cache: "no-store" });
        const data = await res.json();
        detections = data.detections || [];
        latestSequence = data.sequence === undefined || data.sequence === null ? latestSequence : Number(data.sequence);
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

    function beginDrag(ev) {
      if (!editMode) return;
      const zone = selectedZone();
      if (!zone) return;
      const canvas = document.getElementById("overlay");
      const [cx, cy] = eventToCanvasPoint(ev);
      const dpr = window.devicePixelRatio || 1;
      let best = null;
      let bestDist = 18 * dpr;
      (zone.polygon_xy || []).forEach((pt, idx) => {
        const [vx, vy] = scalePoint(Number(pt[0]), Number(pt[1]), canvas);
        const dist = Math.hypot(cx - vx, cy - vy);
        if (dist < bestDist) {
          best = idx;
          bestDist = dist;
        }
      });
      if (best === null) return;
      draggingVertex = best;
      ev.preventDefault();
    }

    function moveDrag(ev) {
      if (!editMode || draggingVertex === null) return;
      const zone = selectedZone();
      if (!zone) return;
      const canvas = document.getElementById("overlay");
      const [cx, cy] = eventToCanvasPoint(ev);
      const [x, y] = unscalePoint(cx, cy, canvas);
      zone.polygon_xy[draggingVertex] = [
        clamp01(x / streamShape.width) * streamShape.width,
        clamp01(y / streamShape.height) * streamShape.height,
      ];
      dirtyZones = true;
      document.getElementById("saveZones").disabled = false;
      document.getElementById("editorState").textContent = "dirty";
      drawOverlay();
      ev.preventDefault();
    }

    function endDrag() {
      draggingVertex = null;
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
    document.getElementById("zoneSelect").addEventListener("change", (ev) => {
      selectedZoneId = ev.target.value;
      drawOverlay();
    });
    document.getElementById("toggleEdit").addEventListener("click", () => {
      editMode = !editMode;
      document.getElementById("toggleEdit").textContent = editMode ? "Done" : "Edit";
      document.getElementById("editorState").textContent = editMode ? "editing" : "view";
      document.getElementById("editorHint").textContent = editMode
        ? "Drag the yellow vertex handles on the selected zone. Save when the overlay matches the new camera view."
        : "Select a zone and enter Edit mode. Drag polygon points on the video to recalibrate after moving the camera.";
      document.getElementById("overlay").style.pointerEvents = editMode ? "auto" : "none";
      drawOverlay();
    });
    document.getElementById("saveZones").addEventListener("click", async () => {
      try {
        await saveZones();
      } catch (err) {
        document.getElementById("editorState").textContent = "error";
        document.getElementById("editorHint").textContent = err.message || String(err);
      }
    });
    document.getElementById("overlay").addEventListener("pointerdown", beginDrag);
    document.getElementById("overlay").addEventListener("pointermove", moveDrag);
    window.addEventListener("pointerup", endDrag);

    loadHeartbeat();
    loadSpatialConfig();
    loadZoneStatus();
    loadDetections();
    loadEvents();
    connectEvents();
    setInterval(loadHeartbeat, 1000);
    setInterval(loadSpatialConfig, 5000);
    setInterval(loadZoneStatus, 700);
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

    def read_body_json(self, max_bytes: int = 200_000) -> object:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("empty request body")
        if length > max_bytes:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

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

    def latest_frame_record(self) -> dict[str, object] | None:
        path = self.frames_path()
        if not path.exists():
            return None
        frames = self.read_json(path)
        if not isinstance(frames, list) or not frames:
            return None
        latest = frames[-1]
        return latest if isinstance(latest, dict) else None

    @staticmethod
    def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
        inside = False
        if len(polygon) < 3:
            return False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    @staticmethod
    def bbox_anchor(det: dict[str, object]) -> tuple[float, float] | None:
        box = det.get("bbox_original_xyxy") or det.get("bbox_xyxy")
        if not isinstance(box, list) or len(box) != 4:
            return None
        try:
            x1, _y1, x2, y2 = [float(v) for v in box]
        except (TypeError, ValueError):
            return None
        return ((x1 + x2) * 0.5, y2)

    def normalized_config_zones(self, config: object) -> list[dict[str, object]]:
        if not isinstance(config, dict):
            return []
        frame = self.frame_shape()
        zones = []
        for zone in config.get("zones", []):
            if not isinstance(zone, dict):
                continue
            polygon_norm = zone.get("polygon_norm", [])
            if not isinstance(polygon_norm, list):
                continue
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
        return zones

    @staticmethod
    def validate_zones(payload: object) -> list[dict[str, object]]:
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        zones = payload.get("zones")
        if not isinstance(zones, list) or not zones:
            raise ValueError("zones must be a non-empty list")
        clean_zones: list[dict[str, object]] = []
        seen: set[str] = set()
        for idx, zone in enumerate(zones):
            if not isinstance(zone, dict):
                raise ValueError(f"zone[{idx}] must be an object")
            zone_id = str(zone.get("id", "")).strip()
            if not zone_id:
                raise ValueError(f"zone[{idx}] is missing id")
            if zone_id in seen:
                raise ValueError(f"duplicate zone id: {zone_id}")
            seen.add(zone_id)
            name = str(zone.get("name", zone_id)).strip() or zone_id
            polygon = zone.get("polygon_norm")
            if not isinstance(polygon, list) or len(polygon) < 3:
                raise ValueError(f"{zone_id} needs at least 3 polygon points")
            clean_polygon = []
            for pt_idx, pt in enumerate(polygon):
                if not isinstance(pt, list) or len(pt) != 2:
                    raise ValueError(f"{zone_id}.polygon_norm[{pt_idx}] must be [x, y]")
                x = float(pt[0])
                y = float(pt[1])
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError(f"{zone_id}.polygon_norm[{pt_idx}] is not finite")
                clean_polygon.append([max(0.0, min(1.0, round(x, 6))), max(0.0, min(1.0, round(y, 6)))])
            clean_zones.append({"id": zone_id, "name": name, "polygon_norm": clean_polygon})
        return clean_zones

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
        elif parsed.path == "/api/zone-status":
            self.handle_zone_status()
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

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/spatial-config":
            self.handle_spatial_config_update()
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
            zones = self.normalized_config_zones(config)
            self.send_json({"frame": frame, "zones": zones, "rules": config.get("rules", [])})  # type: ignore[union-attr]
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 500)

    def handle_spatial_config_update(self) -> None:
        path = self.spatial_rules_path()
        if not path:
            self.send_json({"status": "error", "error": "spatial rules path not found"}, 404)
            return
        try:
            zones = self.validate_zones(self.read_body_json())
            config = self.read_json(path) if path.exists() else {"rules": []}
            if not isinstance(config, dict):
                raise ValueError("existing spatial config is not a JSON object")
            config["zones"] = zones
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp_path.replace(path)
            frame = self.frame_shape()
            self.send_json({"status": "ok", "frame": frame, "zones": self.normalized_config_zones(config), "rules": config.get("rules", [])})
        except Exception as exc:
            self.send_json({"status": "error", "error": str(exc)}, 400)

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

    def handle_zone_status(self) -> None:
        path = self.spatial_rules_path()
        if not path or not path.exists():
            self.send_json({"frame": self.frame_shape(), "zones": []})
            return
        try:
            config = self.read_json(path)
            zones = self.normalized_config_zones(config)
            latest = self.latest_frame_record() or {}
            detections = latest.get("detections", [])
            if not isinstance(detections, list):
                detections = []
            sequence = latest.get("sequence")
            recent_events = self.read_events(40)
            event_by_zone: dict[str, dict[str, object]] = {}
            for event in recent_events:
                zone_id = event.get("zone_id")
                frame_index = event.get("frame_index")
                if not zone_id:
                    continue
                if sequence is not None and frame_index is not None:
                    try:
                        if int(sequence) - int(frame_index) > 90:
                            continue
                    except (TypeError, ValueError):
                        pass
                event_by_zone[str(zone_id)] = event

            status_zones = []
            for zone in zones:
                zone_id = str(zone.get("id", ""))
                polygon = zone.get("polygon_xy", [])
                if not isinstance(polygon, list):
                    polygon = []
                objects = []
                for det in detections:
                    if not isinstance(det, dict):
                        continue
                    anchor = self.bbox_anchor(det)
                    if not anchor:
                        continue
                    if self.point_in_polygon(anchor[0], anchor[1], polygon):  # type: ignore[arg-type]
                        objects.append({
                            "class_name": det.get("class_name"),
                            "class_id": det.get("class_id"),
                            "confidence": det.get("confidence"),
                            "object_id": det.get("object_id", det.get("id")),
                            "bbox_original_xyxy": det.get("bbox_original_xyxy"),
                        })
                state = "alert" if zone_id in event_by_zone else "active" if objects else "idle"
                status_zones.append({
                    "id": zone_id,
                    "name": zone.get("name", zone_id),
                    "state": state,
                    "object_count": len(objects),
                    "objects": objects[:12],
                    "last_event": event_by_zone.get(zone_id),
                })
            self.send_json({"frame": self.frame_shape(), "sequence": sequence, "zones": status_zones})
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
