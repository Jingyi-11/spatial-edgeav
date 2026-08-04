#define _POSIX_C_SOURCE 200809L

#include "pipeline.h"

#include <ctype.h>
#include <string.h>
#include <time.h>

const char *pixel_format_name(PixelFormat format)
{
    switch (format) {
    case PIXEL_FORMAT_YUYV:
        return "YUYV";
    case PIXEL_FORMAT_NV12:
        return "NV12";
    case PIXEL_FORMAT_MJPEG:
        return "MJPEG";
    default:
        return "UNKNOWN";
    }
}

static int equals_ignore_case(const char *left, const char *right)
{
    if (!left || !right) {
        return 0;
    }

    while (*left && *right) {
        if (tolower((unsigned char)*left) != tolower((unsigned char)*right)) {
            return 0;
        }
        left++;
        right++;
    }

    return *left == '\0' && *right == '\0';
}

PixelFormat pixel_format_from_name(const char *name)
{
    if (equals_ignore_case(name, "YUYV") || equals_ignore_case(name, "YUYV422")) {
        return PIXEL_FORMAT_YUYV;
    }
    if (equals_ignore_case(name, "NV12")) {
        return PIXEL_FORMAT_NV12;
    }
    if (equals_ignore_case(name, "MJPEG") || equals_ignore_case(name, "JPEG")) {
        return PIXEL_FORMAT_MJPEG;
    }
    return PIXEL_FORMAT_UNKNOWN;
}

uint64_t monotonic_time_us(void)
{
    struct timespec timestamp;
    clock_gettime(CLOCK_MONOTONIC, &timestamp);
    return (uint64_t)timestamp.tv_sec * 1000000ull + (uint64_t)timestamp.tv_nsec / 1000ull;
}
