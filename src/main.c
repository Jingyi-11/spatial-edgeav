#include "camera_capture.h"
#include "pipeline.h"
#include "yuv.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct CaptureOutput {
    FILE *raw_file;
    const char *preview_path;
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint32_t frames;
    int wrote_preview;
} CaptureOutput;

static void print_usage(const char *program)
{
    printf("Usage:\n");
    printf("  %s probe [--device /dev/video0]\n", program);
    printf("  %s capture [options]\n", program);
    printf("\nOptions:\n");
    printf("  --device PATH       Video device, default /dev/video0\n");
    printf("  --width N           Width, default 640\n");
    printf("  --height N          Height, default 480\n");
    printf("  --fps N             FPS, default 30\n");
    printf("  --frames N          Number of frames, default 60\n");
    printf("  --format NAME       YUYV/NV12/MJPEG, default YUYV\n");
    printf("  --output PATH       Raw output path, default out/video.yuv\n");
    printf("  --preview PATH      Write first YUYV frame as PPM preview\n");
}

static int parse_uint32(const char *text, uint32_t *value)
{
    char *end = NULL;
    errno = 0;
    unsigned long parsed = strtoul(text, &end, 10);
    if (errno || !end || *end != '\0' || parsed == 0 || parsed > UINT32_MAX) {
        return -1;
    }
    *value = (uint32_t)parsed;
    return 0;
}

static int parse_common_options(int argc, char **argv, int start, PipelineConfig *config, const char **preview_path)
{
    for (int index = start; index < argc; index++) {
        if (strcmp(argv[index], "--device") == 0 && index + 1 < argc) {
            config->video_device = argv[++index];
        } else if (strcmp(argv[index], "--width") == 0 && index + 1 < argc) {
            if (parse_uint32(argv[++index], &config->width) != 0) {
                return -1;
            }
        } else if (strcmp(argv[index], "--height") == 0 && index + 1 < argc) {
            if (parse_uint32(argv[++index], &config->height) != 0) {
                return -1;
            }
        } else if (strcmp(argv[index], "--fps") == 0 && index + 1 < argc) {
            if (parse_uint32(argv[++index], &config->fps) != 0) {
                return -1;
            }
        } else if (strcmp(argv[index], "--frames") == 0 && index + 1 < argc) {
            if (parse_uint32(argv[++index], &config->frames) != 0) {
                return -1;
            }
        } else if (strcmp(argv[index], "--format") == 0 && index + 1 < argc) {
            config->pixel_format = pixel_format_from_name(argv[++index]);
            if (config->pixel_format == PIXEL_FORMAT_UNKNOWN) {
                return -1;
            }
        } else if (strcmp(argv[index], "--output") == 0 && index + 1 < argc) {
            config->output_path = argv[++index];
        } else if (strcmp(argv[index], "--preview") == 0 && index + 1 < argc) {
            *preview_path = argv[++index];
        } else {
            return -1;
        }
    }
    return 0;
}

static void on_frame(const VideoFrame *frame, void *userdata)
{
    CaptureOutput *output = userdata;
    if (output->frames == 0) {
        output->first_timestamp_us = frame->timestamp_us;
    }
    output->last_timestamp_us = frame->timestamp_us;
    output->frames++;

    if (output->raw_file) {
        fwrite(frame->data, 1, frame->size, output->raw_file);
    }

    if (!output->wrote_preview && output->preview_path && frame->pixel_format == PIXEL_FORMAT_YUYV) {
        if (yuyv_write_ppm(output->preview_path, frame->data, frame->size, frame->width, frame->height) == 0) {
            output->wrote_preview = 1;
        }
    }
}

static int run_capture(const PipelineConfig *config, const char *preview_path)
{
    CameraCapture *camera = NULL;
    CaptureOutput output = {
        .preview_path = preview_path,
    };

    output.raw_file = fopen(config->output_path, "wb");
    if (!output.raw_file) {
        perror("open output");
        return -1;
    }

    if (camera_open(&camera, config) != 0) {
        fclose(output.raw_file);
        return -1;
    }

    int result = 0;
    if (camera_start(camera) != 0 || camera_capture_frames(camera, on_frame, &output) != 0) {
        result = -1;
    }

    camera_stop(camera);
    camera_close(camera);
    fclose(output.raw_file);

    double elapsed_s = 0.0;
    if (output.frames > 1 && output.last_timestamp_us > output.first_timestamp_us) {
        elapsed_s = (double)(output.last_timestamp_us - output.first_timestamp_us) / 1000000.0;
    }

    printf("Captured %u frames to %s\n", output.frames, config->output_path);
    printf("Format: %s %ux%u @ %u fps\n", pixel_format_name(config->pixel_format), config->width, config->height, config->fps);
    if (elapsed_s > 0.0) {
        printf("Measured FPS: %.2f\n", (double)(output.frames - 1u) / elapsed_s);
    }
    if (output.wrote_preview) {
        printf("Preview frame: %s\n", preview_path);
    }

    return result;
}

int main(int argc, char **argv)
{
    PipelineConfig config = {
        .video_device = "/dev/video0",
        .output_path = "out/video.yuv",
        .width = 640,
        .height = 480,
        .fps = 30,
        .frames = 60,
        .pixel_format = PIXEL_FORMAT_YUYV,
    };
    const char *preview_path = NULL;

    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    if (strcmp(argv[1], "probe") == 0) {
        if (parse_common_options(argc, argv, 2, &config, &preview_path) != 0) {
            print_usage(argv[0]);
            return 1;
        }
        return camera_probe(config.video_device) == 0 ? 0 : 1;
    }

    if (strcmp(argv[1], "capture") == 0) {
        if (parse_common_options(argc, argv, 2, &config, &preview_path) != 0) {
            print_usage(argv[0]);
            return 1;
        }
        return run_capture(&config, preview_path) == 0 ? 0 : 1;
    }

    print_usage(argv[0]);
    return 1;
}
