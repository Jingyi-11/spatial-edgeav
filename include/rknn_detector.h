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

#define RKNN_DETECTOR_MAX_DETECTIONS 100

typedef struct RknnDetection {
    int id;
    int class_id;
    float confidence;
    float bbox_xyxy[4];
    float bbox_xywh[4];
} RknnDetection;

typedef struct RknnFrameResult {
    int status;
    double inference_ms;
    double postprocess_ms;
    uint32_t candidates_before_nms;
    uint32_t detections_before_nms;
    uint32_t detections_after_nms;
    RknnDetection detections[RKNN_DETECTOR_MAX_DETECTIONS];
} RknnFrameResult;

typedef struct RknnDetector RknnDetector;

int rknn_detector_create(
    RknnDetector **detector,
    const char *model_path,
    const char *library_path,
    uint8_t want_float);

int rknn_detector_run(
    RknnDetector *detector,
    const uint8_t *input_data,
    uint32_t input_size,
    RknnFrameResult *result);

void rknn_detector_destroy(RknnDetector *detector);

int rknn_detector_smoke(const RknnSmokeConfig *config);

#ifdef __cplusplus
}
#endif

#endif
