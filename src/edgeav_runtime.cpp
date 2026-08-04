#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

extern "C" {
#include "camera_capture.h"
#include "pipeline.h"
}

namespace {

struct RuntimeConfig {
    const char *device = "/dev/video0";
    const char *report_path = "out/edgeav_runtime_report.json";
    const char *heartbeat_path = "out/edgeav_runtime_heartbeat.json";
    uint32_t width = 640;
    uint32_t height = 480;
    uint32_t fps = 30;
    uint32_t frames = 60;
    PixelFormat pixel_format = PIXEL_FORMAT_YUYV;
    bool simulate = false;
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
    char error[128] = {0};
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
    printf("  --simulate             Use synthetic frames instead of opening V4L2\n");
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
        } else if (strcmp(argv[index], "--simulate") == 0) {
            config->simulate = true;
        } else if (strcmp(argv[index], "--help") == 0) {
            print_usage(argv[0]);
            exit(0);
        } else {
            return false;
        }
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
    fprintf(file, "  \"frames_processed\": %llu,\n", static_cast<unsigned long long>(stats.frames));
    fprintf(file, "  \"bytes_processed\": %llu,\n", static_cast<unsigned long long>(stats.bytes));
    fprintf(file, "  \"last_sequence\": %llu,\n", static_cast<unsigned long long>(stats.last_sequence));
    fprintf(file, "  \"measured_fps\": %.3f,\n", fps_from_stats(stats));
    fprintf(file, "  \"elapsed_ms\": %.3f,\n", elapsed_ms(stats.start_us, stats.end_us));
    fprintf(file, "  \"error\": %s\n", stats.error[0] == '\0' ? "null" : "\"runtime_error\"");
    fprintf(file, "}\n");
    fclose(file);
    return true;
}

void on_frame(const VideoFrame *frame, void *userdata)
{
    auto *stats = static_cast<RuntimeStats *>(userdata);
    if (stats->frames == 0) {
        stats->first_timestamp_us = frame->timestamp_us;
    }
    stats->last_timestamp_us = frame->timestamp_us;
    stats->last_sequence = frame->sequence;
    stats->frames++;
    stats->bytes += frame->size;
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
        on_frame(&frame, stats);
        write_json(config.heartbeat_path, config, *stats, "running");
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
    if (camera_start(camera) != 0 || camera_capture_frames(camera, on_frame, stats) != 0) {
        snprintf(stats->error, sizeof(stats->error), "camera capture failed");
        result = -1;
    }

    camera_stop(camera);
    camera_close(camera);
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

    printf("edgeav_runtime status=%s frames=%llu fps=%.3f report=%s heartbeat=%s\n",
                status,
                static_cast<unsigned long long>(stats.frames),
                fps_from_stats(stats),
                config.report_path,
                config.heartbeat_path);
    return result == 0 ? 0 : 2;
}
