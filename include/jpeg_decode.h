#ifndef JPEG_DECODE_H
#define JPEG_DECODE_H

#include <stddef.h>
#include <stdint.h>

int mjpeg_to_rgb_resized(
    const uint8_t *jpeg,
    size_t jpeg_size,
    uint8_t *rgb,
    uint32_t output_width,
    uint32_t output_height,
    uint32_t *decoded_width,
    uint32_t *decoded_height);

#endif
