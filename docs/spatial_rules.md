# Spatial Rules

Spatial rules convert detector outputs into scene-aware events. The config lives
in:

```text
configs/spatial_rules.json
```

The C++ service deploy target copies it to the board:

```text
/home/kickpi/spatial-edgeav/configs/spatial_rules.json
```

## Coordinate System

Zones use normalized image coordinates:

```text
[0.0, 0.0] = top-left
[1.0, 1.0] = bottom-right
```

For a 1280x720 camera frame, a point `[0.58, 0.38]` maps to:

```text
x = 0.58 * 1280 = 742
y = 0.38 * 720  = 274
```

This keeps the config portable if the camera resolution changes.

If the camera is physically moved or rotated, the zones do not automatically
follow the room objects. They are image-coordinate regions, so the correct
workflow is:

```text
move camera
  -> open dashboard
  -> estimate new normalized zone coordinates
  -> edit configs/spatial_rules.json
  -> redeploy/restart the C++ service
```

The dashboard reloads `/api/spatial-config` every 5 seconds, so visual zone
overlays update after the config changes. The C++ spatial-rule engine still
loads the rules at service startup, so actual event semantics require restarting
`spatial-edgeav-cpp.service`.

## Current Scene Rules

The current config is tuned for the room visible in the dashboard:

| Zone | Purpose | Rule |
| --- | --- | --- |
| `doorway_zone` | Left-side door / entry area | `person_at_entry` |
| `tabletop_zone` | Dining table surface on the right | `bottle_on_table` |
| `walkway_zone` | Lower center walking path | `chair_blocks_walkway` |

The previous `chair_in_left_work_area` rule was intentionally removed because
it generated many low-value events for a static chair-like object. The new
`chair_blocks_walkway` rule requires higher confidence, dwell time, and a longer
cooldown:

```json
{
  "id": "chair_blocks_walkway",
  "type": "zone_dwell",
  "class_name": "chair",
  "zone_id": "walkway_zone",
  "min_confidence": 0.45,
  "dwell_ms": 3000,
  "cooldown_ms": 15000
}
```

## How To Edit Rules

1. Adjust `polygon_norm` for a zone.
2. Pick a COCO class name the current YOLOv8n model can detect, such as
   `person`, `chair`, `bottle`, `tv`, `backpack`, or `cell phone`.
3. Choose the rule type:
   - `zone_intersection`: emit when the object intersects the zone.
   - `zone_dwell`: emit only after the object stays in the zone for `dwell_ms`.
4. Tune `min_confidence`:
   - Lower values increase recall but can create noisy events.
   - Higher values reduce false events but may miss weak detections.
5. Use `cooldown_ms` for static objects so one object does not spam events.

## Why Boxes May Not Show In The Dashboard

The dashboard needs three live artifacts:

```text
latest_frame.jpg            live video frame
edgeav_runtime_frames.json  latest detections / bbox
spatial_rules.json          zone polygons
```

If video and events work but boxes do not, the usual causes are:

- the dashboard service has not been restarted after deploying the overlay
  version;
- the C++ service has not been restarted after deploying the runtime version
  that continuously refreshes `edgeav_runtime_frames.json`;
- the current model frame has no detections above threshold;
- browser cache is still showing the old dashboard page.

Restart both board services after deploying:

```bash
sudo systemctl restart spatial-edgeav-cpp.service
sudo systemctl restart spatial-edgeav-dashboard.service
```

Then hard refresh the browser page.

## Event Highlight TTL

The dashboard keeps recent events in the right-side list, but the yellow bbox
highlight on top of the video is intentionally short-lived. It only draws events
whose `frame_index` is within about 90 frames of the latest detection frame,
roughly 3 seconds at 30 FPS. This prevents old event boxes from remaining on top
of a moved camera view.
