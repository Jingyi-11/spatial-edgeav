#ifndef PIPELINE_H
#define PIPELINE_H

#include <stddef.h>
#include <stdint.h>

typedef enum PixelFormat {
    PIXEL_FORMAT_YUYV,
    PIXEL_FORMAT_NV12,
    PIXEL_FORMAT_MJPEG,
    PIXEL_FORMAT_UNKNOWN
} PixelFormat;

typedef struct PipelineConfig {
    const char *video_device;
    const char *output_path;
    uint32_t width;
    uint32_t height;
    uint32_t fps;
    uint32_t frames;
    PixelFormat pixel_format;
} PipelineConfig;

typedef struct VideoFrame {
    uint8_t *data;
    size_t size;
    uint32_t width;
    uint32_t height;
    PixelFormat pixel_format;
    uint64_t timestamp_us;
    uint64_t sequence;
} VideoFrame;

const char *pixel_format_name(PixelFormat format);
PixelFormat pixel_format_from_name(const char *name);
uint64_t monotonic_time_us(void);

#endif
