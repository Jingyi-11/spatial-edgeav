#include "spatial_engine.h"

#include <algorithm>
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include <fstream>
#include <regex>
#include <sstream>

namespace {

constexpr double kTrackIouThreshold = 0.30;
constexpr uint64_t kTrackTtlFrames = 90;

const char *kCoco80[] = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
};

std::string read_text_file(const char *path)
{
    std::ifstream input(path);
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::string json_escape(const std::string &value)
{
    std::string out;
    out.reserve(value.size() + 8);
    for (char ch : value) {
        switch (ch) {
        case '\\':
            out += "\\\\";
            break;
        case '"':
            out += "\\\"";
            break;
        case '\n':
            out += "\\n";
            break;
        case '\r':
            out += "\\r";
            break;
        case '\t':
            out += "\\t";
            break;
        default:
            out += ch;
            break;
        }
    }
    return out;
}

bool find_array_body(const std::string &text, const char *key, std::string *body)
{
    std::string needle = std::string("\"") + key + "\"";
    size_t key_pos = text.find(needle);
    if (key_pos == std::string::npos) {
        return false;
    }
    size_t start = text.find('[', key_pos);
    if (start == std::string::npos) {
        return false;
    }
    int depth = 0;
    for (size_t index = start; index < text.size(); ++index) {
        if (text[index] == '[') {
            depth++;
        } else if (text[index] == ']') {
            depth--;
            if (depth == 0) {
                *body = text.substr(start + 1, index - start - 1);
                return true;
            }
        }
    }
    return false;
}

std::vector<std::string> top_level_objects(const std::string &array_body)
{
    std::vector<std::string> objects;
    int depth = 0;
    size_t start = std::string::npos;
    for (size_t index = 0; index < array_body.size(); ++index) {
        if (array_body[index] == '{') {
            if (depth == 0) {
                start = index;
            }
            depth++;
        } else if (array_body[index] == '}') {
            depth--;
            if (depth == 0 && start != std::string::npos) {
                objects.push_back(array_body.substr(start, index - start + 1));
                start = std::string::npos;
            }
        }
    }
    return objects;
}

std::string extract_string(const std::string &object, const char *key, const char *fallback = "")
{
    std::regex pattern(std::string("\"") + key + "\"\\s*:\\s*\"([^\"]*)\"");
    std::smatch match;
    if (std::regex_search(object, match, pattern)) {
        return match[1].str();
    }
    return fallback;
}

double extract_number(const std::string &object, const char *key, double fallback = 0.0)
{
    std::regex pattern(std::string("\"") + key + "\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?)");
    std::smatch match;
    if (std::regex_search(object, match, pattern)) {
        return strtod(match[1].str().c_str(), nullptr);
    }
    return fallback;
}

std::vector<double> extract_polygon_norm_xy(const std::string &object)
{
    std::vector<double> points;
    std::string polygon_body;
    if (!find_array_body(object, "polygon_norm", &polygon_body)) {
        return points;
    }
    std::regex point_pattern("\\[\\s*(-?[0-9]+(?:\\.[0-9]+)?)\\s*,\\s*(-?[0-9]+(?:\\.[0-9]+)?)\\s*\\]");
    auto begin = std::sregex_iterator(polygon_body.begin(), polygon_body.end(), point_pattern);
    auto end = std::sregex_iterator();
    for (auto it = begin; it != end; ++it) {
        points.push_back(strtod((*it)[1].str().c_str(), nullptr));
        points.push_back(strtod((*it)[2].str().c_str(), nullptr));
    }
    return points;
}

double box_area(const double bbox[4])
{
    double width = std::max(0.0, bbox[2] - bbox[0]);
    double height = std::max(0.0, bbox[3] - bbox[1]);
    return width * height;
}

double iou(const double a[4], const double b[4])
{
    double x1 = std::max(a[0], b[0]);
    double y1 = std::max(a[1], b[1]);
    double x2 = std::min(a[2], b[2]);
    double y2 = std::min(a[3], b[3]);
    double inter[4] = {x1, y1, x2, y2};
    double inter_area = box_area(inter);
    double union_area = box_area(a) + box_area(b) - inter_area;
    return union_area > 0.0 ? inter_area / union_area : 0.0;
}

void zone_bounds(const SpatialZone &zone, uint32_t width, uint32_t height, double bbox[4])
{
    bbox[0] = static_cast<double>(width);
    bbox[1] = static_cast<double>(height);
    bbox[2] = 0.0;
    bbox[3] = 0.0;
    for (size_t index = 0; index + 1 < zone.polygon_norm_xy.size(); index += 2) {
        double x = zone.polygon_norm_xy[index] * static_cast<double>(width);
        double y = zone.polygon_norm_xy[index + 1] * static_cast<double>(height);
        bbox[0] = std::min(bbox[0], x);
        bbox[1] = std::min(bbox[1], y);
        bbox[2] = std::max(bbox[2], x);
        bbox[3] = std::max(bbox[3], y);
    }
}

bool boxes_intersect(const double a[4], const double b[4])
{
    return !(a[2] < b[0] || a[0] > b[2] || a[3] < b[1] || a[1] > b[3]);
}

const SpatialZone *find_zone(const SpatialConfig &config, const std::string &zone_id)
{
    for (const SpatialZone &zone : config.zones) {
        if (zone.id == zone_id) {
            return &zone;
        }
    }
    return nullptr;
}

int assign_track_id(SpatialTracker *tracker, const SpatialDetection &det, uint64_t sequence, uint64_t ts_ms)
{
    int best_index = -1;
    double best_iou = 0.0;
    for (size_t index = 0; index < tracker->tracks.size(); ++index) {
        SpatialTrack &track = tracker->tracks[index];
        if (track.class_id != det.class_id) {
            continue;
        }
        double overlap = iou(track.bbox_original_xyxy, det.bbox_original_xyxy);
        if (overlap > best_iou) {
            best_iou = overlap;
            best_index = static_cast<int>(index);
        }
    }

    if (best_index < 0 || best_iou < kTrackIouThreshold) {
        SpatialTrack track;
        track.track_id = tracker->next_track_id++;
        track.class_id = det.class_id;
        memcpy(track.bbox_original_xyxy, det.bbox_original_xyxy, sizeof(track.bbox_original_xyxy));
        track.last_sequence = sequence;
        track.first_seen_ms = ts_ms;
        track.last_seen_ms = ts_ms;
        tracker->tracks.push_back(track);
        return track.track_id;
    }

    SpatialTrack &track = tracker->tracks[best_index];
    memcpy(track.bbox_original_xyxy, det.bbox_original_xyxy, sizeof(track.bbox_original_xyxy));
    track.last_sequence = sequence;
    track.last_seen_ms = ts_ms;
    return track.track_id;
}

SpatialTrack *find_track(SpatialTracker *tracker, int track_id)
{
    for (SpatialTrack &track : tracker->tracks) {
        if (track.track_id == track_id) {
            return &track;
        }
    }
    return nullptr;
}

void prune_tracks(SpatialTracker *tracker, uint64_t sequence)
{
    tracker->tracks.erase(
        std::remove_if(
            tracker->tracks.begin(),
            tracker->tracks.end(),
            [sequence](const SpatialTrack &track) {
                return sequence > track.last_sequence && sequence - track.last_sequence > kTrackTtlFrames;
            }),
        tracker->tracks.end());
}

bool rule_is_dwell(const SpatialRule &rule)
{
    return rule.type == "zone_dwell" || rule.type == "dwell_zone" || rule.dwell_ms > 0;
}

} // namespace

const char *spatial_class_name(int class_id)
{
    if (class_id >= 0 && class_id < static_cast<int>(sizeof(kCoco80) / sizeof(kCoco80[0]))) {
        return kCoco80[class_id];
    }
    return "unknown";
}

bool spatial_load_config(const char *path, SpatialConfig *config, std::string *error)
{
    if (!path || !config) {
        if (error) {
            *error = "invalid spatial config arguments";
        }
        return false;
    }
    std::string text = read_text_file(path);
    if (text.empty()) {
        if (error) {
            *error = std::string("empty or unreadable spatial config: ") + path;
        }
        return false;
    }

    SpatialConfig parsed;
    std::string zones_body;
    if (find_array_body(text, "zones", &zones_body)) {
        for (const std::string &object : top_level_objects(zones_body)) {
            SpatialZone zone;
            zone.id = extract_string(object, "id");
            zone.name = extract_string(object, "name", zone.id.c_str());
            zone.polygon_norm_xy = extract_polygon_norm_xy(object);
            if (!zone.id.empty() && zone.polygon_norm_xy.size() >= 6) {
                parsed.zones.push_back(zone);
            }
        }
    }

    std::string rules_body;
    if (find_array_body(text, "rules", &rules_body)) {
        for (const std::string &object : top_level_objects(rules_body)) {
            SpatialRule rule;
            rule.id = extract_string(object, "id");
            rule.type = extract_string(object, "type", "zone_intersection");
            rule.class_name = extract_string(object, "class_name");
            rule.zone_id = extract_string(object, "zone_id");
            rule.severity = extract_string(object, "severity", "info");
            rule.message = extract_string(object, "message");
            rule.min_confidence = extract_number(object, "min_confidence", 0.0);
            rule.dwell_ms = static_cast<uint64_t>(extract_number(object, "dwell_ms", 0.0));
            rule.cooldown_ms = static_cast<uint64_t>(extract_number(object, "cooldown_ms", 1000.0));
            if (!rule.id.empty() && !rule.class_name.empty() && !rule.zone_id.empty()) {
                parsed.rules.push_back(rule);
            }
        }
    }

    if (parsed.zones.empty() || parsed.rules.empty()) {
        if (error) {
            *error = "spatial config must contain at least one valid zone and one valid rule";
        }
        return false;
    }
    *config = parsed;
    return true;
}

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
    std::string *error)
{
    FILE *observations = fopen(observations_path, "a");
    if (!observations) {
        if (error) {
            *error = std::string("open observations jsonl failed: ") + strerror(errno);
        }
        return false;
    }
    FILE *events = fopen(events_path, "a");
    if (!events) {
        fclose(observations);
        if (error) {
            *error = std::string("open events jsonl failed: ") + strerror(errno);
        }
        return false;
    }

    std::vector<int> track_ids;
    track_ids.reserve(detections.size());
    for (const SpatialDetection &det : detections) {
        track_ids.push_back(assign_track_id(tracker, det, sequence, ts_ms));
    }
    prune_tracks(tracker, sequence);

    fprintf(observations, "{\"ts_ms\":%llu,\"frame_index\":%llu,\"width\":%u,\"height\":%u,\"latency_ms\":{\"end_to_end\":%.3f},\"objects\":[",
            static_cast<unsigned long long>(ts_ms),
            static_cast<unsigned long long>(sequence),
            width,
            height,
            end_to_end_ms);
    for (size_t index = 0; index < detections.size(); ++index) {
        const SpatialDetection &det = detections[index];
        fprintf(observations,
                "%s{\"object_id\":%d,\"detection_id\":%d,\"class_id\":%d,\"class_name\":\"%s\",\"confidence\":%.4f,\"bbox_xyxy\":[%.2f,%.2f,%.2f,%.2f],\"bbox_original_xyxy\":[%.2f,%.2f,%.2f,%.2f]}",
                index == 0 ? "" : ",",
                track_ids[index],
                det.detection_id,
                det.class_id,
                spatial_class_name(det.class_id),
                det.confidence,
                det.bbox_model_xyxy[0],
                det.bbox_model_xyxy[1],
                det.bbox_model_xyxy[2],
                det.bbox_model_xyxy[3],
                det.bbox_original_xyxy[0],
                det.bbox_original_xyxy[1],
                det.bbox_original_xyxy[2],
                det.bbox_original_xyxy[3]);
    }
    fprintf(observations, "],\"zones\":[");
    for (size_t zone_index = 0; zone_index < config.zones.size(); ++zone_index) {
        const SpatialZone &zone = config.zones[zone_index];
        double bounds[4];
        zone_bounds(zone, width, height, bounds);
        fprintf(observations,
                "%s{\"id\":\"%s\",\"name\":\"%s\",\"bounds_xyxy\":[%.2f,%.2f,%.2f,%.2f]}",
                zone_index == 0 ? "" : ",",
                json_escape(zone.id).c_str(),
                json_escape(zone.name).c_str(),
                bounds[0],
                bounds[1],
                bounds[2],
                bounds[3]);
    }
    fprintf(observations, "]}\n");

    uint32_t frame_events = 0;
    for (size_t det_index = 0; det_index < detections.size(); ++det_index) {
        const SpatialDetection &det = detections[det_index];
        const char *name = spatial_class_name(det.class_id);
        for (const SpatialRule &rule : config.rules) {
            if (rule.class_name != name || det.confidence < rule.min_confidence) {
                continue;
            }
            const SpatialZone *zone = find_zone(config, rule.zone_id);
            if (!zone) {
                continue;
            }
            double bounds[4];
            zone_bounds(*zone, width, height, bounds);
            if (!boxes_intersect(det.bbox_original_xyxy, bounds)) {
                SpatialTrack *track = find_track(tracker, track_ids[det_index]);
                if (track && track->dwell_zone_id == rule.zone_id) {
                    track->dwell_zone_id.clear();
                    track->dwell_start_ms = 0;
                }
                continue;
            }

            SpatialTrack *track = find_track(tracker, track_ids[det_index]);
            if (!track) {
                continue;
            }
            bool emit = true;
            const char *relation = "intersects";
            if (rule_is_dwell(rule)) {
                relation = "dwells_in";
                if (track->dwell_zone_id != rule.zone_id) {
                    track->dwell_zone_id = rule.zone_id;
                    track->dwell_start_ms = ts_ms;
                }
                emit = ts_ms >= track->dwell_start_ms && ts_ms - track->dwell_start_ms >= rule.dwell_ms;
            }
            if (emit && track->last_event_ms > 0 && ts_ms - track->last_event_ms < rule.cooldown_ms) {
                emit = false;
            }
            if (!emit) {
                continue;
            }
            track->last_event_ms = ts_ms;
            fprintf(events,
                    "{\"ts_ms\":%llu,\"frame_index\":%llu,\"event_id\":\"%llu:%u:%s\",\"type\":\"spatial_rule_triggered\",\"rule_id\":\"%s\",\"severity\":\"%s\",\"message\":\"%s\",\"zone_id\":\"%s\",\"zone_name\":\"%s\",\"relation\":\"%s\",\"object\":{\"object_id\":%d,\"class_id\":%d,\"class_name\":\"%s\",\"confidence\":%.4f,\"bbox_original_xyxy\":[%.2f,%.2f,%.2f,%.2f]}}\n",
                    static_cast<unsigned long long>(ts_ms),
                    static_cast<unsigned long long>(sequence),
                    static_cast<unsigned long long>(sequence),
                    frame_events,
                    json_escape(rule.id).c_str(),
                    json_escape(rule.id).c_str(),
                    json_escape(rule.severity).c_str(),
                    json_escape(rule.message).c_str(),
                    json_escape(zone->id).c_str(),
                    json_escape(zone->name).c_str(),
                    relation,
                    track_ids[det_index],
                    det.class_id,
                    name,
                    det.confidence,
                    det.bbox_original_xyxy[0],
                    det.bbox_original_xyxy[1],
                    det.bbox_original_xyxy[2],
                    det.bbox_original_xyxy[3]);
            frame_events++;
        }
    }

    fclose(events);
    fclose(observations);
    if (summary) {
        summary->observations++;
        summary->events += frame_events;
    }
    return true;
}
