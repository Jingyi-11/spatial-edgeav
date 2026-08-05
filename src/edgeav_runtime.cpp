#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <pthread.h>

#ifdef EDGEAV_ENABLE_LIBJPEG
#include "jpeg_decode.h"
#endif

extern "C" {
#include "camera_capture.h"
#include "pipeline.h"
#include "rknn_detector.h"
#include "yuv.h"
}

namespace {

struct RuntimeConfig {
    const char *device = "/dev/video0";
    const char *report_path = "out/edgeav_runtime_report.json";
    const char *heartbeat_path = "out/edgeav_runtime_heartbeat.json";
    const char *rknn_model_path = nullptr;
    const char *rknn_library_path = "/usr/lib/librknnrt.so";
    const char *rknn_report_path = "out/edgeav_rknn_report.json";
    const char *rknn_input_dump_path = nullptr;
    const char *frames_json_path = "out/edgeav_runtime_frames.json";
    uint32_t width = 640;
    uint32_t height = 480;
    uint32_t fps = 30;
    uint32_t frames = 60;
    uint32_t rknn_runs = 10;
    uint32_t rknn_warmup = 3;
    PixelFormat pixel_format = PIXEL_FORMAT_YUYV;
    bool simulate = false;
    bool letterbox = false;
    bool rknn_every_frame = false;
    bool rknn_latest_frame = false;
};

struct RuntimeStats {
    uint64_t frames = 0;
    uint64_t bytes = 0;
    uint64_t first_timestamp_us = 0;
    uint64_t last_timestamp_us = 0;
    uint64_t start_us = 0;
    uint64_t end_us = 0;
    uint64_t last_sequence = 0;
    bool capture_ok = true;
    bool rknn_input_ready = false;
    bool rknn_attempted = false;
    int rknn_result = 0;
    bool rknn_input_dumped = false;
    uint64_t rknn_frames = 0;
    uint64_t rknn_failures = 0;
    uint64_t detections_total = 0;
    uint64_t skipped_frames = 0;
    double preprocess_ms_total = 0.0;
    double preprocess_decode_ms_total = 0.0;
    double preprocess_resize_or_convert_ms_total = 0.0;
    double inference_ms_total = 0.0;
    double postprocess_ms_total = 0.0;
    double rknn_end_to_end_ms_total = 0.0;
    char error[128] = {0};
};

struct FrameRecord {
    uint64_t sequence = 0;
    double preprocess_ms = 0.0;
    double preprocess_decode_ms = 0.0;
    double preprocess_resize_or_convert_ms = 0.0;
    double inference_ms = 0.0;
    double postprocess_ms = 0.0;
    double end_to_end_ms = 0.0;
    uint32_t detections = 0;
    RknnDetection top_detections[5];
    uint32_t top_detection_count = 0;
};

struct RuntimeContext {
    const RuntimeConfig *config = nullptr;
    RuntimeStats *stats = nullptr;
    uint8_t *rknn_input = nullptr;
    size_t rknn_input_size = 0;
    bool rknn_input_ready = false;
    RknnDetector *detector = nullptr;
    FrameRecord *frame_records = nullptr;
    uint32_t frame_record_capacity = 0;
    uint32_t frame_record_count = 0;
};

struct LatestFrameState {
    const RuntimeConfig *config = nullptr;
    RuntimeStats *stats = nullptr;
    pthread_mutex_t mutex;
    pthread_cond_t condition;
    uint8_t *latest_frame = nullptr;
    size_t latest_frame_size = 0;
    size_t latest_frame_bytes = 0;
    uint32_t width = 0;
    uint32_t height = 0;
    PixelFormat pixel_format = PIXEL_FORMAT_UNKNOWN;
    uint64_t latest_sequence = 0;
    uint64_t published_frames = 0;
    uint64_t consumed_sequence = UINT64_MAX;
    bool has_frame = false;
    bool done = false;
};

struct LatestWorkerArgs {
    LatestFrameState *state = nullptr;
    RknnDetector *detector = nullptr;
    uint8_t *raw_frame = nullptr;
    size_t raw_frame_size = 0;
    uint8_t *rknn_input = nullptr;
    size_t rknn_input_size = 0;
    FrameRecord *frame_records = nullptr;
    uint32_t frame_record_capacity = 0;
    uint32_t *frame_record_count = nullptr;
};

void print_usage(const char *program)
{
    printf("Usage:\n");
    printf("  %s [options]\n", program);
    printf("\nOptions:\n");
    printf("  --device PATH          V4L2 device, default /dev/video0\n");
    printf("  --width N              Capture width, default 640\n");
    printf("  --height N             Capture height, default 480\n");
    printf("  --fps N                Capture FPS, default 30\n");
    printf("  --frames N             Frames to process, default 60\n");
    printf("  --format NAME          YUYV/NV12/MJPEG, default YUYV\n");
    printf("  --report PATH          JSON report path\n");
    printf("  --heartbeat PATH       JSON heartbeat path\n");
    printf("  --frames-json PATH     Per-frame detection/latency JSON path\n");
    printf("  --letterbox            Preserve camera aspect ratio and pad to 640x640\n");
    printf("  --simulate             Use synthetic frames instead of opening V4L2\n");
    printf("  --rknn-model PATH      Optional RKNN model smoke test\n");
    printf("  --rknn-lib PATH        RKNN runtime library, default /usr/lib/librknnrt.so\n");
    printf("  --rknn-report PATH     RKNN tensor/inference JSON report path\n");
    printf("  --rknn-input-dump PATH Write resized RGB RKNN input as PPM when using live YUYV\n");
    printf("  --rknn-every-frame     Run RKNN on every captured YUYV frame\n");
    printf("  --rknn-latest-frame    Decouple capture and RKNN with a latest-frame worker\n");
    printf("  --rknn-runs N          RKNN measured runs, default 10\n");
    printf("  --rknn-warmup N        RKNN warmup runs, default 3\n");
}

bool parse_u32(const char *text, uint32_t *value)
{
    char *end = nullptr;
    errno = 0;
    unsigned long parsed = strtoul(text, &end, 10);
    if (errno || end == nullptr || *end != '\0' || parsed == 0 || parsed > UINT32_MAX) {
        return false;
    }
    *value = static_cast<uint32_t>(parsed);
    return true;
}

bool parse_args(int argc, char **argv, RuntimeConfig *config)
{
    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "--device") == 0 && index + 1 < argc) {
            config->device = argv[++index];
        } else if (strcmp(argv[index], "--width") == 0 && index + 1 < argc) {
            if (!parse_u32(argv[++index], &config->width)) {
                return false;
            }
        } else if (strcmp(argv[index], "--height") == 0 && index + 1 < argc) {
            if (!parse_u32(argv[++index], &config->height)) {
                return false;
            }
        } else if (strcmp(argv[index], "--fps") == 0 && index + 1 < argc) {
            if (!parse_u32(argv[++index], &config->fps)) {
                return false;
            }
        } else if (strcmp(argv[index], "--frames") == 0 && index + 1 < argc) {
            if (!parse_u32(argv[++index], &config->frames)) {
                return false;
            }
        } else if (strcmp(argv[index], "--format") == 0 && index + 1 < argc) {
            config->pixel_format = pixel_format_from_name(argv[++index]);
            if (config->pixel_format == PIXEL_FORMAT_UNKNOWN) {
                return false;
            }
        } else if (strcmp(argv[index], "--report") == 0 && index + 1 < argc) {
            config->report_path = argv[++index];
        } else if (strcmp(argv[index], "--heartbeat") == 0 && index + 1 < argc) {
            config->heartbeat_path = argv[++index];
        } else if (strcmp(argv[index], "--frames-json") == 0 && index + 1 < argc) {
            config->frames_json_path = argv[++index];
        } else if (strcmp(argv[index], "--letterbox") == 0) {
            config->letterbox = true;
        } else if (strcmp(argv[index], "--simulate") == 0) {
            config->simulate = true;
        } else if (strcmp(argv[index], "--rknn-model") == 0 && index + 1 < argc) {
            config->rknn_model_path = argv[++index];
        } else if (strcmp(argv[index], "--rknn-lib") == 0 && index + 1 < argc) {
            config->rknn_library_path = argv[++index];
        } else if (strcmp(argv[index], "--rknn-report") == 0 && index + 1 < argc) {
            config->rknn_report_path = argv[++index];
        } else if (strcmp(argv[index], "--rknn-input-dump") == 0 && index + 1 < argc) {
            config->rknn_input_dump_path = argv[++index];
        } else if (strcmp(argv[index], "--rknn-every-frame") == 0) {
            config->rknn_every_frame = true;
        } else if (strcmp(argv[index], "--rknn-latest-frame") == 0) {
            config->rknn_latest_frame = true;
        } else if (strcmp(argv[index], "--rknn-runs") == 0 && index + 1 < argc) {
            if (!parse_u32(argv[++index], &config->rknn_runs)) {
                return false;
            }
        } else if (strcmp(argv[index], "--rknn-warmup") == 0 && index + 1 < argc) {
            if (!parse_u32(argv[++index], &config->rknn_warmup)) {
                return false;
            }
        } else if (strcmp(argv[index], "--help") == 0) {
            print_usage(argv[0]);
            exit(0);
        } else {
            return false;
        }
    }
    if (config->rknn_latest_frame) {
        config->rknn_every_frame = true;
    }
    return true;
}

double elapsed_ms(uint64_t start_us, uint64_t end_us)
{
    if (end_us <= start_us) {
        return 0.0;
    }
    return static_cast<double>(end_us - start_us) / 1000.0;
}

double fps_from_stats(const RuntimeStats &stats)
{
    if (stats.frames < 2 || stats.last_timestamp_us <= stats.first_timestamp_us) {
        return 0.0;
    }
    double elapsed_s = static_cast<double>(stats.last_timestamp_us - stats.first_timestamp_us) / 1000000.0;
    return static_cast<double>(stats.frames - 1) / elapsed_s;
}

double mean_or_zero(double total, uint64_t count)
{
    return count > 0 ? total / static_cast<double>(count) : 0.0;
}

bool write_json(const char *path, const RuntimeConfig &config, const RuntimeStats &stats, const char *status)
{
    FILE *file = fopen(path, "w");
    if (!file) {
        perror("open json");
        return false;
    }

    fprintf(file, "{\n");
    fprintf(file, "  \"status\": \"%s\",\n", status);
    fprintf(file, "  \"runtime\": \"edgeav_cpp_runtime\",\n");
    fprintf(file, "  \"mode\": \"%s\",\n", config.simulate ? "simulate" : "v4l2");
    fprintf(file, "  \"camera\": {\"device\": \"%s\", \"width\": %u, \"height\": %u, \"fps\": %u, \"format\": \"%s\"},\n",
                 config.device,
                 config.width,
                 config.height,
                 config.fps,
                 pixel_format_name(config.pixel_format));
    fprintf(file, "  \"preprocessing\": {\"image_size\": 640, \"mode\": \"%s\", \"pad_value\": %u},\n",
            config.letterbox ? "letterbox" : "direct_resize",
            config.letterbox ? 114u : 0u);
    fprintf(file, "  \"frames_processed\": %llu,\n", static_cast<unsigned long long>(stats.frames));
    fprintf(file, "  \"bytes_processed\": %llu,\n", static_cast<unsigned long long>(stats.bytes));
    fprintf(file, "  \"last_sequence\": %llu,\n", static_cast<unsigned long long>(stats.last_sequence));
    fprintf(file, "  \"measured_fps\": %.3f,\n", fps_from_stats(stats));
    fprintf(file, "  \"elapsed_ms\": %.3f,\n", elapsed_ms(stats.start_us, stats.end_us));
    if (config.rknn_input_dump_path) {
        fprintf(file, "  \"rknn_input\": {\"ready\": %s, \"dump_path\": \"%s\", \"dumped\": %s},\n",
                stats.rknn_input_ready ? "true" : "false",
                config.rknn_input_dump_path,
                stats.rknn_input_dumped ? "true" : "false");
    } else {
        fprintf(file, "  \"rknn_input\": {\"ready\": %s, \"dump_path\": null, \"dumped\": %s},\n",
                stats.rknn_input_ready ? "true" : "false",
                stats.rknn_input_dumped ? "true" : "false");
    }
    fprintf(file, "  \"rknn_continuous\": {\"enabled\": %s, \"mode\": \"%s\", \"frames\": %llu, \"failures\": %llu, \"skipped_frames\": %llu, \"detections_total\": %llu},\n",
            config.rknn_every_frame ? "true" : "false",
            config.rknn_latest_frame ? "latest_frame_worker" : "synchronous_callback",
            static_cast<unsigned long long>(stats.rknn_frames),
            static_cast<unsigned long long>(stats.rknn_failures),
            static_cast<unsigned long long>(stats.skipped_frames),
            static_cast<unsigned long long>(stats.detections_total));
    fprintf(file, "  \"latency_ms\": {\"preprocess_mean\": %.3f, \"inference_mean\": %.3f, \"postprocess_mean\": %.3f, \"rknn_end_to_end_mean\": %.3f},\n",
            mean_or_zero(stats.preprocess_ms_total, stats.rknn_frames),
            mean_or_zero(stats.inference_ms_total, stats.rknn_frames),
            mean_or_zero(stats.postprocess_ms_total, stats.rknn_frames),
            mean_or_zero(stats.rknn_end_to_end_ms_total, stats.rknn_frames));
    fprintf(file, "  \"preprocess_detail_ms\": {\"decode_mean\": %.3f, \"resize_or_convert_mean\": %.3f},\n",
            mean_or_zero(stats.preprocess_decode_ms_total, stats.rknn_frames),
            mean_or_zero(stats.preprocess_resize_or_convert_ms_total, stats.rknn_frames));
    fprintf(file, "  \"error\": %s\n", stats.error[0] == '\0' ? "null" : "\"runtime_error\"");
    fprintf(file, "}\n");
    fclose(file);
    return true;
}

bool write_frames_json(const char *path, const FrameRecord *records, uint32_t count)
{
    if (!path) {
        return false;
    }
    FILE *file = fopen(path, "w");
    if (!file) {
        perror("open frames json");
        return false;
    }
    fprintf(file, "[\n");
    for (uint32_t index = 0; index < count; ++index) {
        const FrameRecord &record = records[index];
        fprintf(file, "  {\"sequence\": %llu, \"latency_ms\": {\"preprocess\": %.3f, \"preprocess_decode\": %.3f, \"preprocess_resize_or_convert\": %.3f, \"inference\": %.3f, \"postprocess\": %.3f, \"end_to_end\": %.3f}, \"detections\": [",
                static_cast<unsigned long long>(record.sequence),
                record.preprocess_ms,
                record.preprocess_decode_ms,
                record.preprocess_resize_or_convert_ms,
                record.inference_ms,
                record.postprocess_ms,
                record.end_to_end_ms);
        for (uint32_t det_index = 0; det_index < record.top_detection_count; ++det_index) {
            const RknnDetection &det = record.top_detections[det_index];
            fprintf(file, "%s{\"id\": %d, \"class_id\": %d, \"confidence\": %.4f, \"bbox_xyxy\": [%.2f, %.2f, %.2f, %.2f]}",
                    det_index == 0 ? "" : ", ",
                    det.id,
                    det.class_id,
                    det.confidence,
                    det.bbox_xyxy[0],
                    det.bbox_xyxy[1],
                    det.bbox_xyxy[2],
                    det.bbox_xyxy[3]);
        }
        fprintf(file, "]}%s\n", index + 1 < count ? "," : "");
    }
    fprintf(file, "]\n");
    fclose(file);
    return true;
}

bool write_rgb_ppm(const char *path, const uint8_t *rgb, uint32_t width, uint32_t height)
{
    if (!path || !rgb || width == 0 || height == 0) {
        return false;
    }
    FILE *file = fopen(path, "wb");
    if (!file) {
        perror("open rknn input dump");
        return false;
    }
    fprintf(file, "P6\n%u %u\n255\n", width, height);
    size_t bytes = static_cast<size_t>(width) * height * 3u;
    bool ok = fwrite(rgb, 1, bytes, file) == bytes;
    fclose(file);
    return ok;
}

bool pixel_format_supported_for_rknn(PixelFormat format)
{
    if (format == PIXEL_FORMAT_YUYV) {
        return true;
    }
#ifdef EDGEAV_ENABLE_LIBJPEG
    if (format == PIXEL_FORMAT_MJPEG) {
        return true;
    }
#endif
    return false;
}

const char *rknn_input_source_name(PixelFormat format, bool letterbox)
{
    if (format == PIXEL_FORMAT_YUYV) {
        return letterbox ? "v4l2_yuyv_rgb_letterboxed" : "v4l2_yuyv_rgb_resized";
    }
    if (format == PIXEL_FORMAT_MJPEG) {
        return letterbox ? "v4l2_mjpeg_decoded_rgb_letterboxed" : "v4l2_mjpeg_decoded_rgb_resized";
    }
    return "v4l2_unsupported";
}

int preprocess_frame_to_rknn_input(
    const uint8_t *data,
    size_t size,
    uint32_t width,
    uint32_t height,
    PixelFormat pixel_format,
    bool letterbox,
    uint8_t *rknn_input,
    double *decode_ms,
    double *resize_or_convert_ms)
{
    if (decode_ms) {
        *decode_ms = 0.0;
    }
    if (resize_or_convert_ms) {
        *resize_or_convert_ms = 0.0;
    }
    if (pixel_format == PIXEL_FORMAT_YUYV) {
        uint64_t start_us = monotonic_time_us();
        int result = letterbox
            ? yuyv_to_rgb_letterboxed(data, size, width, height, rknn_input, 640, 640, 114)
            : yuyv_to_rgb_resized(data, size, width, height, rknn_input, 640, 640);
        uint64_t end_us = monotonic_time_us();
        if (resize_or_convert_ms) {
            *resize_or_convert_ms = elapsed_ms(start_us, end_us);
        }
        return result;
    }
#ifdef EDGEAV_ENABLE_LIBJPEG
    if (pixel_format == PIXEL_FORMAT_MJPEG) {
        JpegDecodeStats stats;
        int result = mjpeg_to_rgb_resized(data, size, rknn_input, 640, 640, letterbox ? 1 : 0, &stats);
        if (decode_ms) {
            *decode_ms = stats.decode_ms;
        }
        if (resize_or_convert_ms) {
            *resize_or_convert_ms = stats.resize_ms;
        }
        return result;
    }
#endif
    return -1;
}

void on_frame(const VideoFrame *frame, void *userdata)
{
    auto *context = static_cast<RuntimeContext *>(userdata);
    RuntimeStats *stats = context->stats;
    if (stats->frames == 0) {
        stats->first_timestamp_us = frame->timestamp_us;
    }
    stats->last_timestamp_us = frame->timestamp_us;
    stats->last_sequence = frame->sequence;
    stats->frames++;
    stats->bytes += frame->size;

    if (context->config->rknn_model_path && context->rknn_input && pixel_format_supported_for_rknn(frame->pixel_format)) {
        uint64_t preprocess_start_us = monotonic_time_us();
        double decode_ms = 0.0;
        double resize_or_convert_ms = 0.0;
        int preprocess_result = preprocess_frame_to_rknn_input(
            frame->data,
            frame->size,
            frame->width,
            frame->height,
            frame->pixel_format,
            context->config->letterbox,
            context->rknn_input,
            &decode_ms,
            &resize_or_convert_ms);
        uint64_t preprocess_end_us = monotonic_time_us();
        if (preprocess_result == 0) {
            double preprocess_ms = elapsed_ms(preprocess_start_us, preprocess_end_us);
            context->rknn_input_ready = true;
            stats->rknn_input_ready = true;

            if (context->config->rknn_input_dump_path && !stats->rknn_input_dumped) {
                stats->rknn_input_dumped = write_rgb_ppm(context->config->rknn_input_dump_path, context->rknn_input, 640, 640);
            }

            if (context->config->rknn_every_frame && context->detector) {
                uint64_t end_to_end_start_us = preprocess_start_us;
                RknnFrameResult result;
                int rknn_result = rknn_detector_run(
                    context->detector,
                    context->rknn_input,
                    static_cast<uint32_t>(context->rknn_input_size),
                    &result);
                uint64_t end_to_end_end_us = monotonic_time_us();
                double end_to_end_ms = elapsed_ms(end_to_end_start_us, end_to_end_end_us);

                stats->rknn_attempted = true;
                stats->rknn_result = rknn_result;
                if (rknn_result != 0) {
                    stats->rknn_failures++;
                    snprintf(stats->error, sizeof(stats->error), "rknn_detector_run failed");
                } else {
                    stats->rknn_frames++;
                    stats->detections_total += result.detections_after_nms;
                    stats->preprocess_ms_total += preprocess_ms;
                    stats->preprocess_decode_ms_total += decode_ms;
                    stats->preprocess_resize_or_convert_ms_total += resize_or_convert_ms;
                    stats->inference_ms_total += result.inference_ms;
                    stats->postprocess_ms_total += result.postprocess_ms;
                    stats->rknn_end_to_end_ms_total += end_to_end_ms;

                    if (context->frame_records && context->frame_record_count < context->frame_record_capacity) {
                        FrameRecord &record = context->frame_records[context->frame_record_count++];
                        record.sequence = frame->sequence;
                        record.preprocess_ms = preprocess_ms;
                        record.preprocess_decode_ms = decode_ms;
                        record.preprocess_resize_or_convert_ms = resize_or_convert_ms;
                        record.inference_ms = result.inference_ms;
                        record.postprocess_ms = result.postprocess_ms;
                        record.end_to_end_ms = end_to_end_ms;
                        record.detections = result.detections_after_nms;
                        record.top_detection_count = result.detections_after_nms < 5 ? result.detections_after_nms : 5;
                        for (uint32_t index = 0; index < record.top_detection_count; ++index) {
                            record.top_detections[index] = result.detections[index];
                        }
                    }
                }
            }
        }
    }

    write_json(context->config->heartbeat_path, *context->config, *stats, "running");
}

void record_capture_stats(RuntimeStats *stats, const VideoFrame *frame)
{
    if (stats->frames == 0) {
        stats->first_timestamp_us = frame->timestamp_us;
    }
    stats->last_timestamp_us = frame->timestamp_us;
    stats->last_sequence = frame->sequence;
    stats->frames++;
    stats->bytes += frame->size;
}

void on_latest_frame(const VideoFrame *frame, void *userdata)
{
    auto *state = static_cast<LatestFrameState *>(userdata);
    pthread_mutex_lock(&state->mutex);
    record_capture_stats(state->stats, frame);

    if (!pixel_format_supported_for_rknn(frame->pixel_format) || frame->size > state->latest_frame_size) {
        pthread_mutex_unlock(&state->mutex);
        return;
    }
    memcpy(state->latest_frame, frame->data, frame->size);
    state->latest_frame_bytes = frame->size;
    state->width = frame->width;
    state->height = frame->height;
    state->pixel_format = frame->pixel_format;
    state->latest_sequence = frame->sequence;
    state->published_frames++;
    state->has_frame = true;
    pthread_cond_signal(&state->condition);
    pthread_mutex_unlock(&state->mutex);
}

void store_frame_result(
    FrameRecord *frame_records,
    uint32_t frame_record_capacity,
    uint32_t *frame_record_count,
    uint64_t sequence,
    double preprocess_ms,
    double decode_ms,
    double resize_or_convert_ms,
    double end_to_end_ms,
    const RknnFrameResult &result)
{
    if (!frame_records || !frame_record_count || *frame_record_count >= frame_record_capacity) {
        return;
    }
    FrameRecord &record = frame_records[(*frame_record_count)++];
    record.sequence = sequence;
    record.preprocess_ms = preprocess_ms;
    record.preprocess_decode_ms = decode_ms;
    record.preprocess_resize_or_convert_ms = resize_or_convert_ms;
    record.inference_ms = result.inference_ms;
    record.postprocess_ms = result.postprocess_ms;
    record.end_to_end_ms = end_to_end_ms;
    record.detections = result.detections_after_nms;
    record.top_detection_count = result.detections_after_nms < 5 ? result.detections_after_nms : 5;
    for (uint32_t index = 0; index < record.top_detection_count; ++index) {
        record.top_detections[index] = result.detections[index];
    }
}

void accumulate_rknn_stats(
    RuntimeStats *stats,
    double preprocess_ms,
    double decode_ms,
    double resize_or_convert_ms,
    double end_to_end_ms,
    const RknnFrameResult &result)
{
    stats->rknn_attempted = true;
    stats->rknn_result = result.status;
    stats->rknn_frames++;
    stats->detections_total += result.detections_after_nms;
    stats->preprocess_ms_total += preprocess_ms;
    stats->preprocess_decode_ms_total += decode_ms;
    stats->preprocess_resize_or_convert_ms_total += resize_or_convert_ms;
    stats->inference_ms_total += result.inference_ms;
    stats->postprocess_ms_total += result.postprocess_ms;
    stats->rknn_end_to_end_ms_total += end_to_end_ms;
}

void latest_frame_worker(
    LatestFrameState *state,
    RknnDetector *detector,
    uint8_t *raw_frame,
    size_t raw_frame_size,
    uint8_t *rknn_input,
    size_t rknn_input_size,
    FrameRecord *frame_records,
    uint32_t frame_record_capacity,
    uint32_t *frame_record_count)
{
    while (true) {
        uint64_t sequence = 0;
        uint32_t width = 0;
        uint32_t height = 0;
        PixelFormat pixel_format = PIXEL_FORMAT_UNKNOWN;
        size_t frame_bytes = 0;
        pthread_mutex_lock(&state->mutex);
        while (!state->done && (!state->has_frame || state->latest_sequence == state->consumed_sequence)) {
            pthread_cond_wait(&state->condition, &state->mutex);
        }
        if (state->done && (!state->has_frame || state->latest_sequence == state->consumed_sequence)) {
            pthread_mutex_unlock(&state->mutex);
            break;
        }
        size_t copy_size = state->latest_frame_bytes < raw_frame_size ? state->latest_frame_bytes : raw_frame_size;
        memcpy(raw_frame, state->latest_frame, copy_size);
        sequence = state->latest_sequence;
        width = state->width;
        height = state->height;
        pixel_format = state->pixel_format;
        frame_bytes = copy_size;
        state->consumed_sequence = sequence;
        pthread_mutex_unlock(&state->mutex);

        uint64_t preprocess_start_us = monotonic_time_us();
        double decode_ms = 0.0;
        double resize_or_convert_ms = 0.0;
        int preprocess_result = preprocess_frame_to_rknn_input(
            raw_frame,
            frame_bytes,
            width,
            height,
            pixel_format,
            state->config->letterbox,
            rknn_input,
            &decode_ms,
            &resize_or_convert_ms);
        uint64_t preprocess_end_us = monotonic_time_us();
        if (preprocess_result != 0) {
            pthread_mutex_lock(&state->mutex);
            state->stats->rknn_failures++;
            snprintf(state->stats->error, sizeof(state->stats->error), "latest frame preprocess failed");
            pthread_mutex_unlock(&state->mutex);
            continue;
        }
        double preprocess_ms = elapsed_ms(preprocess_start_us, preprocess_end_us);

        pthread_mutex_lock(&state->mutex);
        state->stats->rknn_input_ready = true;
        if (state->config->rknn_input_dump_path && !state->stats->rknn_input_dumped) {
            state->stats->rknn_input_dumped = write_rgb_ppm(state->config->rknn_input_dump_path, rknn_input, 640, 640);
        }
        pthread_mutex_unlock(&state->mutex);

        uint64_t end_to_end_start_us = preprocess_start_us;
        RknnFrameResult frame_result;
        int rknn_result = rknn_detector_run(detector, rknn_input, static_cast<uint32_t>(rknn_input_size), &frame_result);
        uint64_t end_to_end_end_us = monotonic_time_us();
        double end_to_end_ms = elapsed_ms(end_to_end_start_us, end_to_end_end_us);

        pthread_mutex_lock(&state->mutex);
        if (rknn_result != 0) {
            state->stats->rknn_attempted = true;
            state->stats->rknn_result = rknn_result;
            state->stats->rknn_failures++;
            snprintf(state->stats->error, sizeof(state->stats->error), "rknn_detector_run failed");
            pthread_mutex_unlock(&state->mutex);
            continue;
        }
        accumulate_rknn_stats(state->stats, preprocess_ms, decode_ms, resize_or_convert_ms, end_to_end_ms, frame_result);
        store_frame_result(
            frame_records,
            frame_record_capacity,
            frame_record_count,
            sequence,
            preprocess_ms,
            decode_ms,
            resize_or_convert_ms,
            end_to_end_ms,
            frame_result);
        write_json(state->config->heartbeat_path, *state->config, *state->stats, "running");
        pthread_mutex_unlock(&state->mutex);
    }
}

void *latest_frame_worker_entry(void *userdata)
{
    auto *args = static_cast<LatestWorkerArgs *>(userdata);
    latest_frame_worker(
        args->state,
        args->detector,
        args->raw_frame,
        args->raw_frame_size,
        args->rknn_input,
        args->rknn_input_size,
        args->frame_records,
        args->frame_record_capacity,
        args->frame_record_count);
    return nullptr;
}

size_t simulated_frame_size(const RuntimeConfig &config)
{
    if (config.pixel_format == PIXEL_FORMAT_NV12) {
        return static_cast<size_t>(config.width) * config.height * 3u / 2u;
    }
    if (config.pixel_format == PIXEL_FORMAT_MJPEG) {
        return static_cast<size_t>(config.width) * config.height / 8u;
    }
    return static_cast<size_t>(config.width) * config.height * 2u;
}

int run_simulated(const RuntimeConfig &config, RuntimeStats *stats)
{
    size_t frame_size = simulated_frame_size(config);
    uint8_t *data = static_cast<uint8_t *>(calloc(frame_size, 1));
    if (!data) {
        snprintf(stats->error, sizeof(stats->error), "simulated frame allocation failed");
        return -1;
    }
    uint32_t sleep_us = config.fps > 0 ? 1000000u / config.fps : 33333u;
    for (uint32_t index = 0; index < config.frames; ++index) {
        uint64_t now = monotonic_time_us();
        VideoFrame frame = {
            data,
            frame_size,
            config.width,
            config.height,
            config.pixel_format,
            now,
            index,
        };
        RuntimeContext context = {
            &config,
            stats,
            nullptr,
            0,
            false,
            nullptr,
            nullptr,
            0,
            0,
        };
        on_frame(&frame, &context);
        usleep(sleep_us);
    }
    free(data);
    return 0;
}

int run_v4l2(const RuntimeConfig &config, RuntimeStats *stats)
{
    PipelineConfig pipeline_config = {
        config.device,
        nullptr,
        config.width,
        config.height,
        config.fps,
        config.frames,
        config.pixel_format,
    };

    CameraCapture *camera = nullptr;
    if (camera_open(&camera, &pipeline_config) != 0) {
        snprintf(stats->error, sizeof(stats->error), "camera_open failed");
        return -1;
    }

    int result = 0;
    RuntimeContext context = {
        &config,
        stats,
        nullptr,
        0,
        false,
        nullptr,
        nullptr,
        0,
        0,
    };
    uint8_t *rknn_input = nullptr;
    uint8_t *latest_frame_buffer = nullptr;
    uint8_t *worker_frame_buffer = nullptr;
    FrameRecord *frame_records = nullptr;
    LatestFrameState latest_state;
    LatestWorkerArgs worker_args;
    pthread_t worker_thread;
    bool latest_state_initialized = false;
    bool worker_started = false;
    if (config.rknn_model_path && pixel_format_supported_for_rknn(config.pixel_format)) {
        context.rknn_input_size = 640u * 640u * 3u;
        rknn_input = static_cast<uint8_t *>(calloc(context.rknn_input_size, 1));
        context.rknn_input = rknn_input;
        if (!rknn_input) {
            snprintf(stats->error, sizeof(stats->error), "rknn input allocation failed");
            camera_close(camera);
            return -1;
        }
        if (config.rknn_every_frame) {
            int detector_result = rknn_detector_create(
                &context.detector,
                config.rknn_model_path,
                config.rknn_library_path,
                0);
            if (detector_result != 0) {
                snprintf(stats->error, sizeof(stats->error), "rknn_detector_create failed");
                camera_close(camera);
                free(rknn_input);
                return detector_result;
            }
            frame_records = static_cast<FrameRecord *>(calloc(config.frames, sizeof(FrameRecord)));
            if (!frame_records) {
                snprintf(stats->error, sizeof(stats->error), "frame records allocation failed");
                rknn_detector_destroy(context.detector);
                camera_close(camera);
                free(rknn_input);
                return -1;
            }
            context.frame_records = frame_records;
            context.frame_record_capacity = config.frames;

            if (config.rknn_latest_frame) {
                size_t raw_frame_size = static_cast<size_t>(config.width) * config.height * 2u;
                size_t mjpeg_buffer_size = static_cast<size_t>(config.width) * config.height * 3u;
                if (config.pixel_format == PIXEL_FORMAT_MJPEG && mjpeg_buffer_size > raw_frame_size) {
                    raw_frame_size = mjpeg_buffer_size;
                }
                latest_frame_buffer = static_cast<uint8_t *>(calloc(raw_frame_size, 1));
                worker_frame_buffer = static_cast<uint8_t *>(calloc(raw_frame_size, 1));
                if (!latest_frame_buffer || !worker_frame_buffer) {
                    snprintf(stats->error, sizeof(stats->error), "latest frame allocation failed");
                    rknn_detector_destroy(context.detector);
                    camera_close(camera);
                    free(worker_frame_buffer);
                    free(latest_frame_buffer);
                    free(frame_records);
                    free(rknn_input);
                    return -1;
                }
                latest_state.config = &config;
                latest_state.stats = stats;
                pthread_mutex_init(&latest_state.mutex, nullptr);
                pthread_cond_init(&latest_state.condition, nullptr);
                latest_state_initialized = true;
                latest_state.latest_frame = latest_frame_buffer;
                latest_state.latest_frame_size = raw_frame_size;
                worker_args.state = &latest_state;
                worker_args.detector = context.detector;
                worker_args.raw_frame = worker_frame_buffer;
                worker_args.raw_frame_size = raw_frame_size;
                worker_args.rknn_input = rknn_input;
                worker_args.rknn_input_size = context.rknn_input_size;
                worker_args.frame_records = frame_records;
                worker_args.frame_record_capacity = config.frames;
                worker_args.frame_record_count = &context.frame_record_count;
                if (pthread_create(&worker_thread, nullptr, latest_frame_worker_entry, &worker_args) != 0) {
                    snprintf(stats->error, sizeof(stats->error), "latest frame worker start failed");
                    pthread_cond_destroy(&latest_state.condition);
                    pthread_mutex_destroy(&latest_state.mutex);
                    rknn_detector_destroy(context.detector);
                    camera_close(camera);
                    free(worker_frame_buffer);
                    free(latest_frame_buffer);
                    free(frame_records);
                    free(rknn_input);
                    return -1;
                }
                worker_started = true;
            }
        }
    }

    FrameCallback callback = config.rknn_latest_frame ? on_latest_frame : on_frame;
    void *callback_userdata = config.rknn_latest_frame ? static_cast<void *>(&latest_state) : static_cast<void *>(&context);
    if (camera_start(camera) != 0 || camera_capture_frames(camera, callback, callback_userdata) != 0) {
        snprintf(stats->error, sizeof(stats->error), "camera capture failed");
        result = -1;
    }

    camera_stop(camera);
    camera_close(camera);

    if (config.rknn_latest_frame) {
        if (latest_state_initialized) {
            pthread_mutex_lock(&latest_state.mutex);
            latest_state.done = true;
            pthread_cond_signal(&latest_state.condition);
            pthread_mutex_unlock(&latest_state.mutex);
        }
        if (worker_started) {
            pthread_join(worker_thread, nullptr);
        }
        stats->skipped_frames = stats->frames > stats->rknn_frames ? stats->frames - stats->rknn_frames : 0;
        context.rknn_input_ready = stats->rknn_input_ready;
    }

    stats->rknn_input_ready = context.rknn_input_ready;

    if (config.rknn_every_frame && frame_records) {
        write_frames_json(config.frames_json_path, frame_records, context.frame_record_count);
        if (stats->rknn_failures > 0 && result == 0) {
            result = stats->rknn_result == 0 ? -1 : stats->rknn_result;
        }
    }

    if (result == 0 && config.rknn_model_path && context.rknn_input_ready && !config.rknn_every_frame) {
        if (config.rknn_input_dump_path && !stats->rknn_input_dumped) {
            stats->rknn_input_dumped = write_rgb_ppm(config.rknn_input_dump_path, context.rknn_input, 640, 640);
        }
        RknnSmokeConfig rknn_config = {
            config.rknn_model_path,
            config.rknn_library_path,
            config.rknn_report_path,
            context.rknn_input,
            static_cast<uint32_t>(context.rknn_input_size),
            rknn_input_source_name(config.pixel_format, config.letterbox),
            config.rknn_runs,
            config.rknn_warmup,
            0,
        };
        int rknn_result = rknn_detector_smoke(&rknn_config);
        stats->rknn_attempted = true;
        stats->rknn_result = rknn_result;
        if (rknn_result != 0) {
            snprintf(stats->error, sizeof(stats->error), "rknn_detector_smoke failed");
            result = rknn_result;
        }
    } else if (result == 0 && config.rknn_model_path && !pixel_format_supported_for_rknn(config.pixel_format)) {
        snprintf(stats->error, sizeof(stats->error), "rknn live input format unsupported by this build");
        result = -1;
    } else if (result == 0 && config.rknn_model_path && !context.rknn_input_ready && !config.rknn_every_frame) {
        snprintf(stats->error, sizeof(stats->error), "rknn live input was not prepared");
        result = -1;
    }

    rknn_detector_destroy(context.detector);
    if (latest_state_initialized) {
        pthread_cond_destroy(&latest_state.condition);
        pthread_mutex_destroy(&latest_state.mutex);
    }
    free(frame_records);
    free(worker_frame_buffer);
    free(latest_frame_buffer);
    free(rknn_input);
    return result;
}

} // namespace

int main(int argc, char **argv)
{
    RuntimeConfig config;
    if (!parse_args(argc, argv, &config)) {
        print_usage(argv[0]);
        return 1;
    }

    RuntimeStats stats;
    stats.start_us = monotonic_time_us();
    int result = config.simulate ? run_simulated(config, &stats) : run_v4l2(config, &stats);
    stats.end_us = monotonic_time_us();
    stats.capture_ok = result == 0;
    const char *status = result == 0 ? "ok" : "error";

    write_json(config.heartbeat_path, config, stats, status);
    write_json(config.report_path, config, stats, status);

    int rknn_result = 0;
    bool rknn_attempted = false;
    if (config.rknn_model_path && config.simulate) {
        RknnSmokeConfig rknn_config = {
            config.rknn_model_path,
            config.rknn_library_path,
            config.rknn_report_path,
            nullptr,
            0,
            "zero_filled_synthetic",
            config.rknn_runs,
            config.rknn_warmup,
            0,
        };
        rknn_result = rknn_detector_smoke(&rknn_config);
        rknn_attempted = true;
    } else if (config.rknn_model_path && stats.rknn_attempted) {
        rknn_result = stats.rknn_result;
        rknn_attempted = true;
    }

    printf("edgeav_runtime status=%s frames=%llu fps=%.3f report=%s heartbeat=%s",
                status,
                static_cast<unsigned long long>(stats.frames),
                fps_from_stats(stats),
                config.report_path,
                config.heartbeat_path);
    if (config.rknn_model_path && rknn_attempted) {
        printf(" rknn_status=%s rknn_report=%s", rknn_result == 0 ? "ok" : "error", config.rknn_report_path);
    } else if (config.rknn_model_path) {
        printf(" rknn_status=skipped");
    }
    printf("\n");
    if (result != 0) {
        return 2;
    }
    return rknn_result == 0 ? 0 : rknn_result;
}
