#ifndef SPATIAL_ENGINE_H
#define SPATIAL_ENGINE_H

#include <stdint.h>

#include <string>
#include <vector>

struct SpatialDetection {
    int detection_id = 0;
    int class_id = 0;
    float confidence = 0.0f;
    double bbox_model_xyxy[4] = {0.0, 0.0, 0.0, 0.0};
    double bbox_original_xyxy[4] = {0.0, 0.0, 0.0, 0.0};
};

struct SpatialZone {
    std::string id;
    std::string name;
    std::vector<double> polygon_norm_xy;
};

struct SpatialRule {
    std::string id;
    std::string type;
    std::string class_name;
    std::string zone_id;
    std::string severity;
    std::string message;
    double min_confidence = 0.0;
    uint64_t dwell_ms = 0;
    uint64_t cooldown_ms = 1000;
};

struct SpatialConfig {
    std::vector<SpatialZone> zones;
    std::vector<SpatialRule> rules;
};

struct SpatialTrack {
    int track_id = 0;
    int class_id = -1;
    double bbox_original_xyxy[4] = {0.0, 0.0, 0.0, 0.0};
    uint64_t last_sequence = 0;
    uint64_t first_seen_ms = 0;
    uint64_t last_seen_ms = 0;
    std::string dwell_zone_id;
    uint64_t dwell_start_ms = 0;
    uint64_t last_event_ms = 0;
};

struct SpatialTracker {
    int next_track_id = 1;
    std::vector<SpatialTrack> tracks;
};

struct SpatialEventSummary {
    uint32_t observations = 0;
    uint32_t events = 0;
};

bool spatial_load_config(const char *path, SpatialConfig *config, std::string *error);

bool spatial_append_frame_jsonl(
    const char *observations_path,
    const char *events_path,
    const SpatialConfig &config,
    SpatialTracker *tracker,
    uint64_t sequence,
    uint64_t ts_ms,
    uint32_t width,
    uint32_t height,
    double end_to_end_ms,
    const std::vector<SpatialDetection> &detections,
    SpatialEventSummary *summary,
    std::string *error);

const char *spatial_class_name(int class_id);

#endif
