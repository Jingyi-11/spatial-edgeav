#ifndef RKNN_DETECTOR_H
#define RKNN_DETECTOR_H

#include <stdint.h>

typedef struct RknnSmokeConfig {
    const char *model_path;
    const char *library_path;
    const char *report_path;
    uint32_t runs;
    uint32_t warmup;
    uint8_t want_float;
} RknnSmokeConfig;

int rknn_detector_smoke(const RknnSmokeConfig *config);

#endif
