#ifndef RKNN_DETECTOR_H
#define RKNN_DETECTOR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct RknnSmokeConfig {
    const char *model_path;
    const char *library_path;
    const char *report_path;
    const uint8_t *input_data;
    uint32_t input_size;
    const char *input_source;
    uint32_t runs;
    uint32_t warmup;
    uint8_t want_float;
} RknnSmokeConfig;

int rknn_detector_smoke(const RknnSmokeConfig *config);

#ifdef __cplusplus
}
#endif

#endif
