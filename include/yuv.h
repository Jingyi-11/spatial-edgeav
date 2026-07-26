#ifndef YUV_H
#define YUV_H

#include <stddef.h>
#include <stdint.h>

int yuyv_write_ppm(const char *path, const uint8_t *yuyv, size_t size, uint32_t width, uint32_t height);

#endif
