#include "yuv.h"

#include <stdio.h>

static uint8_t clamp_int(int value)
{
    if (value < 0) {
        return 0;
    }
    if (value > 255) {
        return 255;
    }
    return (uint8_t)value;
}

static void yuv_to_rgb(uint8_t y, uint8_t u, uint8_t v, uint8_t *red, uint8_t *green, uint8_t *blue)
{
    int c = (int)y - 16;
    int d = (int)u - 128;
    int e = (int)v - 128;

    *red = clamp_int((298 * c + 409 * e + 128) >> 8);
    *green = clamp_int((298 * c - 100 * d - 208 * e + 128) >> 8);
    *blue = clamp_int((298 * c + 516 * d + 128) >> 8);
}

int yuyv_write_ppm(const char *path, const uint8_t *yuyv, size_t size, uint32_t width, uint32_t height)
{
    size_t expected_size = (size_t)width * (size_t)height * 2u;
    if (!path || !yuyv || size < expected_size || width == 0 || height == 0) {
        return -1;
    }

    FILE *file = fopen(path, "wb");
    if (!file) {
        return -1;
    }

    fprintf(file, "P6\n%u %u\n255\n", width, height);

    for (size_t index = 0; index < expected_size; index += 4) {
        uint8_t y0 = yuyv[index + 0];
        uint8_t u = yuyv[index + 1];
        uint8_t y1 = yuyv[index + 2];
        uint8_t v = yuyv[index + 3];
        uint8_t rgb[6];

        yuv_to_rgb(y0, u, v, &rgb[0], &rgb[1], &rgb[2]);
        yuv_to_rgb(y1, u, v, &rgb[3], &rgb[4], &rgb[5]);
        fwrite(rgb, 1, sizeof(rgb), file);
    }

    fclose(file);
    return 0;
}

int yuyv_to_rgb_resized(
    const uint8_t *yuyv,
    size_t size,
    uint32_t width,
    uint32_t height,
    uint8_t *rgb,
    uint32_t output_width,
    uint32_t output_height)
{
    size_t expected_size = (size_t)width * (size_t)height * 2u;
    if (!yuyv || !rgb || size < expected_size || width == 0 || height == 0 || output_width == 0 || output_height == 0) {
        return -1;
    }

    for (uint32_t out_y = 0; out_y < output_height; ++out_y) {
        uint32_t src_y = (uint32_t)(((uint64_t)out_y * height) / output_height);
        for (uint32_t out_x = 0; out_x < output_width; ++out_x) {
            uint32_t src_x = (uint32_t)(((uint64_t)out_x * width) / output_width);
            uint32_t pair_x = src_x & ~1u;
            size_t yuyv_offset = ((size_t)src_y * width + pair_x) * 2u;
            uint8_t y_value = yuyv[yuyv_offset + (src_x & 1u) * 2u];
            uint8_t u = yuyv[yuyv_offset + 1u];
            uint8_t v = yuyv[yuyv_offset + 3u];
            size_t rgb_offset = ((size_t)out_y * output_width + out_x) * 3u;
            yuv_to_rgb(y_value, u, v, &rgb[rgb_offset + 0u], &rgb[rgb_offset + 1u], &rgb[rgb_offset + 2u]);
        }
    }

    return 0;
}
