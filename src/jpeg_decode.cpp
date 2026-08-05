#include "jpeg_decode.h"

#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <jpeglib.h>

struct JpegErrorManager {
    jpeg_error_mgr public_fields;
    jmp_buf jump_buffer;
};

static void jpeg_error_exit(j_common_ptr cinfo)
{
    JpegErrorManager *manager = reinterpret_cast<JpegErrorManager *>(cinfo->err);
    longjmp(manager->jump_buffer, 1);
}

static void resize_rgb_nearest(
    const uint8_t *src,
    uint32_t src_width,
    uint32_t src_height,
    uint8_t *dst,
    uint32_t dst_width,
    uint32_t dst_height)
{
    for (uint32_t y = 0; y < dst_height; ++y) {
        uint32_t src_y = static_cast<uint32_t>((static_cast<uint64_t>(y) * src_height) / dst_height);
        if (src_y >= src_height) {
            src_y = src_height - 1;
        }
        for (uint32_t x = 0; x < dst_width; ++x) {
            uint32_t src_x = static_cast<uint32_t>((static_cast<uint64_t>(x) * src_width) / dst_width);
            if (src_x >= src_width) {
                src_x = src_width - 1;
            }
            const uint8_t *src_pixel = src + (static_cast<size_t>(src_y) * src_width + src_x) * 3u;
            uint8_t *dst_pixel = dst + (static_cast<size_t>(y) * dst_width + x) * 3u;
            dst_pixel[0] = src_pixel[0];
            dst_pixel[1] = src_pixel[1];
            dst_pixel[2] = src_pixel[2];
        }
    }
}

int mjpeg_to_rgb_resized(
    const uint8_t *jpeg,
    size_t jpeg_size,
    uint8_t *rgb,
    uint32_t output_width,
    uint32_t output_height,
    uint32_t *decoded_width,
    uint32_t *decoded_height)
{
    if (!jpeg || jpeg_size == 0 || !rgb || output_width == 0 || output_height == 0) {
        return -1;
    }

    jpeg_decompress_struct cinfo;
    JpegErrorManager error_manager;
    memset(&cinfo, 0, sizeof(cinfo));
    cinfo.err = jpeg_std_error(&error_manager.public_fields);
    error_manager.public_fields.error_exit = jpeg_error_exit;

    if (setjmp(error_manager.jump_buffer)) {
        jpeg_destroy_decompress(&cinfo);
        return -2;
    }

    jpeg_create_decompress(&cinfo);
    jpeg_mem_src(&cinfo, jpeg, static_cast<unsigned long>(jpeg_size));
    if (jpeg_read_header(&cinfo, TRUE) != JPEG_HEADER_OK) {
        jpeg_destroy_decompress(&cinfo);
        return -3;
    }
    cinfo.out_color_space = JCS_RGB;
    jpeg_start_decompress(&cinfo);

    uint32_t width = cinfo.output_width;
    uint32_t height = cinfo.output_height;
    uint32_t channels = cinfo.output_components;
    if (width == 0 || height == 0 || channels != 3) {
        jpeg_finish_decompress(&cinfo);
        jpeg_destroy_decompress(&cinfo);
        return -4;
    }

    size_t row_stride = static_cast<size_t>(width) * channels;
    size_t decoded_size = row_stride * height;
    uint8_t *decoded = static_cast<uint8_t *>(malloc(decoded_size));
    if (!decoded) {
        jpeg_finish_decompress(&cinfo);
        jpeg_destroy_decompress(&cinfo);
        return -5;
    }

    while (cinfo.output_scanline < cinfo.output_height) {
        uint8_t *row = decoded + static_cast<size_t>(cinfo.output_scanline) * row_stride;
        JSAMPROW rows[1] = { row };
        jpeg_read_scanlines(&cinfo, rows, 1);
    }

    jpeg_finish_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);

    resize_rgb_nearest(decoded, width, height, rgb, output_width, output_height);
    free(decoded);

    if (decoded_width) {
        *decoded_width = width;
    }
    if (decoded_height) {
        *decoded_height = height;
    }
    return 0;
}
