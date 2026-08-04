#include "rknn_detector.h"
#include "rknn_api_compat.h"

extern "C" {
#include "pipeline.h"
}

#include <dlfcn.h>
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace {

typedef int (*RknnInitFn)(rknn_context *, void *, uint32_t, uint32_t, RknnInitExtend *);
typedef int (*RknnDestroyFn)(rknn_context);
typedef int (*RknnQueryFn)(rknn_context, RknnQueryCmd, void *, uint32_t);
typedef int (*RknnInputsSetFn)(rknn_context, uint32_t, RknnInput *);
typedef int (*RknnRunFn)(rknn_context, RknnRunExtend *);
typedef int (*RknnOutputsGetFn)(rknn_context, uint32_t, RknnOutput *, RknnOutputExtend *);
typedef int (*RknnOutputsReleaseFn)(rknn_context, uint32_t, RknnOutput *);

struct RknnApi {
    void *handle = nullptr;
    RknnInitFn init = nullptr;
    RknnDestroyFn destroy = nullptr;
    RknnQueryFn query = nullptr;
    RknnInputsSetFn inputs_set = nullptr;
    RknnRunFn run = nullptr;
    RknnOutputsGetFn outputs_get = nullptr;
    RknnOutputsReleaseFn outputs_release = nullptr;
};

struct TensorSummary {
    RknnTensorAttr attr;
};

constexpr uint32_t kYoloImageSize = 640;
constexpr float kConfidenceThreshold = 0.25f;
constexpr float kIouThreshold = 0.45f;
constexpr float kContainmentThreshold = 0.85f;
constexpr uint32_t kMaxDetections = 100;
constexpr uint32_t kMaxYoloGroups = 8;
constexpr uint32_t kMaxCandidates = 8400;

struct Detection {
    int id = 0;
    int class_id = 0;
    float confidence = 0.0f;
    float x1 = 0.0f;
    float y1 = 0.0f;
    float x2 = 0.0f;
    float y2 = 0.0f;
};

struct CandidateStat {
    uint32_t height = 0;
    uint32_t width = 0;
    uint32_t positions = 0;
    uint32_t candidates = 0;
};

struct DecodeSummary {
    bool attempted = false;
    bool supported = false;
    const char *type = "unsupported";
    uint32_t output_groups = 0;
    uint32_t candidates_before_nms = 0;
    uint32_t detections_before_nms = 0;
    uint32_t candidate_stat_count = 0;
    CandidateStat candidate_stats[kMaxYoloGroups];
    uint32_t detection_count = 0;
    Detection detections[kMaxDetections];
};

struct YoloGroup {
    int box_index = -1;
    int score_index = -1;
    int score_sum_index = -1;
    uint32_t height = 0;
    uint32_t width = 0;
};

const char *tensor_type_name(RknnTensorType type)
{
    switch (type) {
    case RKNN_TENSOR_FLOAT32:
        return "FLOAT32";
    case RKNN_TENSOR_FLOAT16:
        return "FLOAT16";
    case RKNN_TENSOR_INT8:
        return "INT8";
    case RKNN_TENSOR_UINT8:
        return "UINT8";
    case RKNN_TENSOR_INT16:
        return "INT16";
    case RKNN_TENSOR_UINT16:
        return "UINT16";
    case RKNN_TENSOR_INT32:
        return "INT32";
    case RKNN_TENSOR_UINT32:
        return "UINT32";
    case RKNN_TENSOR_INT64:
        return "INT64";
    case RKNN_TENSOR_BOOL:
        return "BOOL";
    case RKNN_TENSOR_INT4:
        return "INT4";
    default:
        return "UNKNOWN";
    }
}

const char *tensor_format_name(RknnTensorFormat format)
{
    switch (format) {
    case RKNN_TENSOR_NCHW:
        return "NCHW";
    case RKNN_TENSOR_NHWC:
        return "NHWC";
    case RKNN_TENSOR_NC1HWC2:
        return "NC1HWC2";
    case RKNN_TENSOR_UNDEFINED:
        return "UNDEFINED";
    default:
        return "UNKNOWN";
    }
}

const char *qnt_type_name(RknnTensorQntType type)
{
    switch (type) {
    case RKNN_TENSOR_QNT_NONE:
        return "NONE";
    case RKNN_TENSOR_QNT_DFP:
        return "DFP";
    case RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC:
        return "AFFINE_ASYMMETRIC";
    default:
        return "UNKNOWN";
    }
}

void *load_symbol(void *handle, const char *name)
{
    dlerror();
    void *symbol = dlsym(handle, name);
    const char *error = dlerror();
    if (error != nullptr) {
        fprintf(stderr, "Missing RKNN symbol %s: %s\n", name, error);
        return nullptr;
    }
    return symbol;
}

int load_api(const char *library_path, RknnApi *api)
{
    api->handle = dlopen(library_path, RTLD_NOW | RTLD_LOCAL);
    if (!api->handle) {
        fprintf(stderr, "dlopen %s failed: %s\n", library_path, dlerror());
        return -1;
    }

    api->init = reinterpret_cast<RknnInitFn>(load_symbol(api->handle, "rknn_init"));
    api->destroy = reinterpret_cast<RknnDestroyFn>(load_symbol(api->handle, "rknn_destroy"));
    api->query = reinterpret_cast<RknnQueryFn>(load_symbol(api->handle, "rknn_query"));
    api->inputs_set = reinterpret_cast<RknnInputsSetFn>(load_symbol(api->handle, "rknn_inputs_set"));
    api->run = reinterpret_cast<RknnRunFn>(load_symbol(api->handle, "rknn_run"));
    api->outputs_get = reinterpret_cast<RknnOutputsGetFn>(load_symbol(api->handle, "rknn_outputs_get"));
    api->outputs_release = reinterpret_cast<RknnOutputsReleaseFn>(load_symbol(api->handle, "rknn_outputs_release"));

    if (!api->init || !api->destroy || !api->query || !api->inputs_set || !api->run || !api->outputs_get || !api->outputs_release) {
        dlclose(api->handle);
        *api = RknnApi{};
        return -1;
    }
    return 0;
}

void unload_api(RknnApi *api)
{
    if (api->handle) {
        dlclose(api->handle);
    }
    *api = RknnApi{};
}

size_t tensor_type_bytes(RknnTensorType type)
{
    switch (type) {
    case RKNN_TENSOR_FLOAT32:
    case RKNN_TENSOR_INT32:
    case RKNN_TENSOR_UINT32:
        return 4;
    case RKNN_TENSOR_FLOAT16:
    case RKNN_TENSOR_INT16:
    case RKNN_TENSOR_UINT16:
        return 2;
    case RKNN_TENSOR_INT64:
        return 8;
    case RKNN_TENSOR_INT4:
        return 1;
    default:
        return 1;
    }
}

bool is_nchw_4d_with_channels(const RknnTensorAttr &attr, uint32_t channels)
{
    return attr.n_dims == 4 && attr.fmt == RKNN_TENSOR_NCHW && attr.dims[0] == 1 && attr.dims[1] == channels && attr.dims[2] > 0 && attr.dims[3] > 0;
}

float tensor_value(const RknnTensorAttr &attr, const RknnOutput &output, uint32_t channel, uint32_t y, uint32_t x)
{
    uint32_t height = attr.dims[2];
    uint32_t width = attr.dims[3];
    size_t offset = (static_cast<size_t>(channel) * height + y) * width + x;

    if (output.want_float) {
        const auto *data = static_cast<const float *>(output.buf);
        return data[offset];
    }

    const auto *base = static_cast<const uint8_t *>(output.buf);
    switch (attr.type) {
    case RKNN_TENSOR_INT8: {
        int32_t raw = static_cast<int32_t>(reinterpret_cast<const int8_t *>(base)[offset]);
        return (static_cast<float>(raw) - static_cast<float>(attr.zp)) * attr.scale;
    }
    case RKNN_TENSOR_UINT8: {
        int32_t raw = static_cast<int32_t>(base[offset]);
        return (static_cast<float>(raw) - static_cast<float>(attr.zp)) * attr.scale;
    }
    case RKNN_TENSOR_INT16: {
        int32_t raw = static_cast<int32_t>(reinterpret_cast<const int16_t *>(base)[offset]);
        return (static_cast<float>(raw) - static_cast<float>(attr.zp)) * attr.scale;
    }
    case RKNN_TENSOR_UINT16: {
        int32_t raw = static_cast<int32_t>(reinterpret_cast<const uint16_t *>(base)[offset]);
        return (static_cast<float>(raw) - static_cast<float>(attr.zp)) * attr.scale;
    }
    case RKNN_TENSOR_FLOAT32:
        return reinterpret_cast<const float *>(base)[offset];
    default:
        return 0.0f;
    }
}

float clampf(float value, float low, float high)
{
    if (value < low) {
        return low;
    }
    if (value > high) {
        return high;
    }
    return value;
}

float box_iou(const Detection &a, const Detection &b)
{
    float ix1 = a.x1 > b.x1 ? a.x1 : b.x1;
    float iy1 = a.y1 > b.y1 ? a.y1 : b.y1;
    float ix2 = a.x2 < b.x2 ? a.x2 : b.x2;
    float iy2 = a.y2 < b.y2 ? a.y2 : b.y2;
    float iw = ix2 > ix1 ? ix2 - ix1 : 0.0f;
    float ih = iy2 > iy1 ? iy2 - iy1 : 0.0f;
    float intersection = iw * ih;
    float aw = a.x2 > a.x1 ? a.x2 - a.x1 : 0.0f;
    float ah = a.y2 > a.y1 ? a.y2 - a.y1 : 0.0f;
    float bw = b.x2 > b.x1 ? b.x2 - b.x1 : 0.0f;
    float bh = b.y2 > b.y1 ? b.y2 - b.y1 : 0.0f;
    float area_a = aw * ah;
    float area_b = bw * bh;
    float union_area = area_a + area_b - intersection;
    return union_area > 0.0f ? intersection / union_area : 0.0f;
}

float box_intersection_over_smaller_area(const Detection &a, const Detection &b)
{
    float ix1 = a.x1 > b.x1 ? a.x1 : b.x1;
    float iy1 = a.y1 > b.y1 ? a.y1 : b.y1;
    float ix2 = a.x2 < b.x2 ? a.x2 : b.x2;
    float iy2 = a.y2 < b.y2 ? a.y2 : b.y2;
    float iw = ix2 > ix1 ? ix2 - ix1 : 0.0f;
    float ih = iy2 > iy1 ? iy2 - iy1 : 0.0f;
    float intersection = iw * ih;
    float aw = a.x2 > a.x1 ? a.x2 - a.x1 : 0.0f;
    float ah = a.y2 > a.y1 ? a.y2 - a.y1 : 0.0f;
    float bw = b.x2 > b.x1 ? b.x2 - b.x1 : 0.0f;
    float bh = b.y2 > b.y1 ? b.y2 - b.y1 : 0.0f;
    float area_a = aw * ah;
    float area_b = bw * bh;
    float smaller = area_a < area_b ? area_a : area_b;
    return smaller > 0.0f ? intersection / smaller : 0.0f;
}

uint32_t group_rockchip_yolov8_outputs(const TensorSummary *outputs, uint32_t output_count, YoloGroup groups[kMaxYoloGroups])
{
    uint32_t group_count = 0;
    for (uint32_t index = 0; index < output_count; ++index) {
        const RknnTensorAttr &candidate = outputs[index].attr;
        if (!is_nchw_4d_with_channels(candidate, 64) || group_count >= kMaxYoloGroups) {
            continue;
        }

        YoloGroup group;
        group.box_index = static_cast<int>(index);
        group.height = candidate.dims[2];
        group.width = candidate.dims[3];

        for (uint32_t other = 0; other < output_count; ++other) {
            const RknnTensorAttr &attr = outputs[other].attr;
            if (attr.n_dims != 4 || attr.fmt != RKNN_TENSOR_NCHW || attr.dims[2] != group.height || attr.dims[3] != group.width) {
                continue;
            }
            if (attr.dims[1] == 80) {
                group.score_index = static_cast<int>(other);
            } else if (attr.dims[1] == 1) {
                group.score_sum_index = static_cast<int>(other);
            }
        }

        if (group.score_index >= 0) {
            groups[group_count++] = group;
        }
    }

    for (uint32_t i = 0; i < group_count; ++i) {
        for (uint32_t j = i + 1; j < group_count; ++j) {
            if (groups[j].height * groups[j].width > groups[i].height * groups[i].width) {
                YoloGroup temp = groups[i];
                groups[i] = groups[j];
                groups[j] = temp;
            }
        }
    }
    return group_count;
}

void decode_dfl_distances(
    const RknnTensorAttr &box_attr,
    const RknnOutput &box_output,
    uint32_t x,
    uint32_t y,
    float distances[4])
{
    constexpr uint32_t kSides = 4;
    uint32_t bins = box_attr.dims[1] / kSides;
    for (uint32_t side = 0; side < kSides; ++side) {
        float max_logit = -INFINITY;
        for (uint32_t bin = 0; bin < bins; ++bin) {
            float value = tensor_value(box_attr, box_output, side * bins + bin, y, x);
            max_logit = value > max_logit ? value : max_logit;
        }

        float sum = 0.0f;
        float weighted_sum = 0.0f;
        for (uint32_t bin = 0; bin < bins; ++bin) {
            float probability = expf(tensor_value(box_attr, box_output, side * bins + bin, y, x) - max_logit);
            sum += probability;
            weighted_sum += probability * static_cast<float>(bin);
        }
        distances[side] = sum > 0.0f ? weighted_sum / sum : 0.0f;
    }
}

int compare_detection_confidence_desc(const void *left, const void *right)
{
    const auto *a = static_cast<const Detection *>(left);
    const auto *b = static_cast<const Detection *>(right);
    if (a->confidence < b->confidence) {
        return 1;
    }
    if (a->confidence > b->confidence) {
        return -1;
    }
    return 0;
}

uint32_t nms(const Detection *candidates, uint32_t candidate_count, Detection kept[kMaxDetections])
{
    uint32_t kept_count = 0;
    for (uint32_t index = 0; index < candidate_count; ++index) {
        const Detection &candidate = candidates[index];
        bool suppress = false;
        for (uint32_t kept_index = 0; kept_index < kept_count; ++kept_index) {
            const Detection &current = kept[kept_index];
            if (candidate.class_id != current.class_id) {
                continue;
            }
            if (box_iou(candidate, current) >= kIouThreshold || box_intersection_over_smaller_area(candidate, current) >= kContainmentThreshold) {
                suppress = true;
                break;
            }
        }
        if (!suppress) {
            Detection kept_detection = candidate;
            kept_detection.id = static_cast<int>(kept_count);
            kept[kept_count++] = kept_detection;
            if (kept_count >= kMaxDetections) {
                break;
            }
        }
    }
    return kept_count;
}

DecodeSummary decode_rockchip_yolov8_outputs(
    const TensorSummary *output_attrs,
    const RknnOutput *rknn_outputs,
    uint32_t output_count)
{
    DecodeSummary summary;
    summary.attempted = true;
    YoloGroup groups[kMaxYoloGroups];
    uint32_t group_count = group_rockchip_yolov8_outputs(output_attrs, output_count, groups);
    summary.output_groups = group_count;
    if (group_count == 0) {
        return summary;
    }

    summary.supported = true;
    summary.type = "rockchip_yolov8_optimized_head";

    Detection candidates[kMaxCandidates];
    uint32_t candidate_count = 0;
    for (uint32_t group_index = 0; group_index < group_count; ++group_index) {
        const YoloGroup &group = groups[group_index];
        const RknnTensorAttr &box_attr = output_attrs[group.box_index].attr;
        const RknnTensorAttr &score_attr = output_attrs[group.score_index].attr;
        const RknnOutput &box_output = rknn_outputs[group.box_index];
        const RknnOutput &score_output = rknn_outputs[group.score_index];
        const RknnTensorAttr *score_sum_attr = group.score_sum_index >= 0 ? &output_attrs[group.score_sum_index].attr : nullptr;
        const RknnOutput *score_sum_output = group.score_sum_index >= 0 ? &rknn_outputs[group.score_sum_index] : nullptr;

        CandidateStat stat;
        stat.height = group.height;
        stat.width = group.width;
        stat.positions = group.height * group.width;

        float stride_x = static_cast<float>(kYoloImageSize) / static_cast<float>(group.width);
        float stride_y = static_cast<float>(kYoloImageSize) / static_cast<float>(group.height);

        for (uint32_t y = 0; y < group.height; ++y) {
            for (uint32_t x = 0; x < group.width; ++x) {
                int best_class = 0;
                float best_score = tensor_value(score_attr, score_output, 0, y, x);
                for (uint32_t class_id = 1; class_id < score_attr.dims[1]; ++class_id) {
                    float score = tensor_value(score_attr, score_output, class_id, y, x);
                    if (score > best_score) {
                        best_score = score;
                        best_class = static_cast<int>(class_id);
                    }
                }
                if (best_score < kConfidenceThreshold) {
                    continue;
                }
                if (score_sum_attr && score_sum_output && tensor_value(*score_sum_attr, *score_sum_output, 0, y, x) < kConfidenceThreshold) {
                    continue;
                }

                float distances[4];
                decode_dfl_distances(box_attr, box_output, x, y, distances);

                float grid_x = static_cast<float>(x) + 0.5f;
                float grid_y = static_cast<float>(y) + 0.5f;
                Detection detection;
                detection.class_id = best_class;
                detection.confidence = best_score;
                detection.x1 = clampf((grid_x - distances[0]) * stride_x, 0.0f, static_cast<float>(kYoloImageSize));
                detection.y1 = clampf((grid_y - distances[1]) * stride_y, 0.0f, static_cast<float>(kYoloImageSize));
                detection.x2 = clampf((grid_x + distances[2]) * stride_x, 0.0f, static_cast<float>(kYoloImageSize));
                detection.y2 = clampf((grid_y + distances[3]) * stride_y, 0.0f, static_cast<float>(kYoloImageSize));
                if (detection.x2 <= detection.x1 || detection.y2 <= detection.y1) {
                    continue;
                }
                if (candidate_count < kMaxCandidates) {
                    candidates[candidate_count++] = detection;
                }
                stat.candidates++;
            }
        }
        if (summary.candidate_stat_count < kMaxYoloGroups) {
            summary.candidate_stats[summary.candidate_stat_count++] = stat;
        }
    }

    summary.candidates_before_nms = candidate_count;
    summary.detections_before_nms = candidate_count;
    qsort(candidates, candidate_count, sizeof(candidates[0]), compare_detection_confidence_desc);
    summary.detection_count = nms(candidates, candidate_count, summary.detections);
    return summary;
}

uint32_t fallback_input_size(const RknnTensorAttr *attr)
{
    if (attr->size > 0) {
        return attr->size;
    }
    if (attr->n_elems > 0) {
        return attr->n_elems * static_cast<uint32_t>(tensor_type_bytes(attr->type));
    }
    return 640u * 640u * 3u;
}

void write_tensor_json(FILE *file, const char *label, const RknnTensorAttr *attr, bool trailing_comma)
{
    fprintf(file, "    {\n");
    fprintf(file, "      \"kind\": \"%s\",\n", label);
    fprintf(file, "      \"index\": %u,\n", attr->index);
    fprintf(file, "      \"name\": \"%s\",\n", attr->name);
    fprintf(file, "      \"n_dims\": %u,\n", attr->n_dims);
    fprintf(file, "      \"dims\": [");
    for (uint32_t index = 0; index < attr->n_dims && index < RKNN_MAX_DIMS; ++index) {
        fprintf(file, "%s%u", index == 0 ? "" : ", ", attr->dims[index]);
    }
    fprintf(file, "],\n");
    fprintf(file, "      \"n_elems\": %u,\n", attr->n_elems);
    fprintf(file, "      \"size\": %u,\n", attr->size);
    fprintf(file, "      \"size_with_stride\": %u,\n", attr->size_with_stride);
    fprintf(file, "      \"fmt\": \"%s\",\n", tensor_format_name(attr->fmt));
    fprintf(file, "      \"type\": \"%s\",\n", tensor_type_name(attr->type));
    fprintf(file, "      \"qnt_type\": \"%s\",\n", qnt_type_name(attr->qnt_type));
    fprintf(file, "      \"zp\": %d,\n", attr->zp);
    fprintf(file, "      \"scale\": %.9g\n", attr->scale);
    fprintf(file, "    }%s\n", trailing_comma ? "," : "");
}

void write_report(
    const char *path,
    const RknnSmokeConfig *config,
    const RknnSdkVersion *version,
    const RknnInputOutputNum *io_num,
    const TensorSummary *inputs,
    const TensorSummary *outputs,
    int status,
    const char *stage,
    double inference_mean_ms,
    const DecodeSummary *decode_summary)
{
    FILE *file = fopen(path, "w");
    if (!file) {
        perror("open rknn report");
        return;
    }
    fprintf(file, "{\n");
    fprintf(file, "  \"status\": \"%s\",\n", status == 0 ? "ok" : "error");
    fprintf(file, "  \"stage\": \"%s\",\n", stage);
    fprintf(file, "  \"model_path\": \"%s\",\n", config->model_path);
    fprintf(file, "  \"library_path\": \"%s\",\n", config->library_path);
    fprintf(file, "  \"runs\": %u,\n", config->runs);
    fprintf(file, "  \"warmup\": %u,\n", config->warmup);
    fprintf(file, "  \"sdk\": {\"api_version\": \"%s\", \"drv_version\": \"%s\"},\n", version->api_version, version->drv_version);
    fprintf(file, "  \"io_num\": {\"n_input\": %u, \"n_output\": %u},\n", io_num->n_input, io_num->n_output);
    fprintf(file, "  \"inference_ms\": {\"mean\": %.3f},\n", inference_mean_ms);
    if (decode_summary && decode_summary->attempted) {
        fprintf(file, "  \"postprocess\": {\n");
        fprintf(file, "    \"status\": \"%s\",\n", decode_summary->supported ? "ok" : "unsupported");
        fprintf(file, "    \"type\": \"%s\",\n", decode_summary->type);
        fprintf(file, "    \"image_size\": %u,\n", kYoloImageSize);
        fprintf(file, "    \"candidate_filter\": \"class_score_and_score_sum\",\n");
        fprintf(file, "    \"confidence_threshold\": %.3f,\n", kConfidenceThreshold);
        fprintf(file, "    \"iou_threshold\": %.3f,\n", kIouThreshold);
        fprintf(file, "    \"containment_threshold\": %.3f,\n", kContainmentThreshold);
        fprintf(file, "    \"output_groups\": %u,\n", decode_summary->output_groups);
        fprintf(file, "    \"candidate_stats\": [");
        for (uint32_t index = 0; index < decode_summary->candidate_stat_count; ++index) {
            const CandidateStat &stat = decode_summary->candidate_stats[index];
            fprintf(file, "%s{\"grid\": [%u, %u], \"positions\": %u, \"candidates\": %u}",
                    index == 0 ? "" : ", ",
                    stat.height,
                    stat.width,
                    stat.positions,
                    stat.candidates);
        }
        fprintf(file, "],\n");
        fprintf(file, "    \"candidates_before_nms\": %u,\n", decode_summary->candidates_before_nms);
        fprintf(file, "    \"detections_before_nms\": %u,\n", decode_summary->detections_before_nms);
        fprintf(file, "    \"detections_after_nms\": %u,\n", decode_summary->detection_count);
        fprintf(file, "    \"max_detections\": %u\n", kMaxDetections);
        fprintf(file, "  },\n");
        fprintf(file, "  \"detections\": [\n");
        for (uint32_t index = 0; index < decode_summary->detection_count; ++index) {
            const Detection &det = decode_summary->detections[index];
            fprintf(file, "    {\"id\": %d, \"class_id\": %d, \"confidence\": %.4f, \"bbox_xyxy\": [%.2f, %.2f, %.2f, %.2f], \"bbox_xywh\": [%.2f, %.2f, %.2f, %.2f]}%s\n",
                    det.id,
                    det.class_id,
                    det.confidence,
                    det.x1,
                    det.y1,
                    det.x2,
                    det.y2,
                    det.x1,
                    det.y1,
                    det.x2 - det.x1,
                    det.y2 - det.y1,
                    index + 1 < decode_summary->detection_count ? "," : "");
        }
        fprintf(file, "  ],\n");
    }
    fprintf(file, "  \"tensors\": [\n");
    uint32_t total = io_num->n_input + io_num->n_output;
    uint32_t written = 0;
    for (uint32_t index = 0; index < io_num->n_input; ++index) {
        write_tensor_json(file, "input", &inputs[index].attr, ++written < total);
    }
    for (uint32_t index = 0; index < io_num->n_output; ++index) {
        write_tensor_json(file, "output", &outputs[index].attr, ++written < total);
    }
    fprintf(file, "  ]\n");
    fprintf(file, "}\n");
    fclose(file);
}

} // namespace

int rknn_detector_smoke(const RknnSmokeConfig *config)
{
    if (!config || !config->model_path || !config->library_path || !config->report_path) {
        fprintf(stderr, "invalid rknn smoke config\n");
        return 2;
    }

    RknnApi api;
    if (load_api(config->library_path, &api) != 0) {
        return 3;
    }

    rknn_context ctx = 0;
    int ret = api.init(&ctx, const_cast<char *>(config->model_path), 0, 0, nullptr);
    if (ret != RKNN_SUCC) {
        fprintf(stderr, "rknn_init failed: %d\n", ret);
        unload_api(&api);
        return 4;
    }

    RknnSdkVersion version;
    memset(&version, 0, sizeof(version));
    ret = api.query(ctx, RKNN_QUERY_SDK_VERSION, &version, sizeof(version));
    if (ret != RKNN_SUCC) {
        fprintf(stderr, "RKNN_QUERY_SDK_VERSION failed: %d\n", ret);
    }

    RknnInputOutputNum io_num;
    memset(&io_num, 0, sizeof(io_num));
    ret = api.query(ctx, RKNN_QUERY_IN_OUT_NUM, &io_num, sizeof(io_num));
    if (ret != RKNN_SUCC || io_num.n_input == 0 || io_num.n_output == 0 || io_num.n_input > 8 || io_num.n_output > 32) {
        fprintf(stderr, "RKNN_QUERY_IN_OUT_NUM failed or returned unexpected counts: ret=%d inputs=%u outputs=%u\n", ret, io_num.n_input, io_num.n_output);
        api.destroy(ctx);
        unload_api(&api);
        return 5;
    }

    TensorSummary *inputs = static_cast<TensorSummary *>(calloc(io_num.n_input, sizeof(TensorSummary)));
    TensorSummary *outputs = static_cast<TensorSummary *>(calloc(io_num.n_output, sizeof(TensorSummary)));
    if (!inputs || !outputs) {
        free(inputs);
        free(outputs);
        api.destroy(ctx);
        unload_api(&api);
        return 6;
    }

    for (uint32_t index = 0; index < io_num.n_input; ++index) {
        inputs[index].attr.index = index;
        ret = api.query(ctx, RKNN_QUERY_INPUT_ATTR, &inputs[index].attr, sizeof(inputs[index].attr));
        if (ret != RKNN_SUCC) {
            fprintf(stderr, "RKNN_QUERY_INPUT_ATTR %u failed: %d\n", index, ret);
        }
    }
    for (uint32_t index = 0; index < io_num.n_output; ++index) {
        outputs[index].attr.index = index;
        ret = api.query(ctx, RKNN_QUERY_OUTPUT_ATTR, &outputs[index].attr, sizeof(outputs[index].attr));
        if (ret != RKNN_SUCC) {
            fprintf(stderr, "RKNN_QUERY_OUTPUT_ATTR %u failed: %d\n", index, ret);
        }
    }

    uint32_t input_size = fallback_input_size(&inputs[0].attr);
    uint8_t *input_buffer = static_cast<uint8_t *>(calloc(input_size, 1));
    if (!input_buffer) {
        free(inputs);
        free(outputs);
        api.destroy(ctx);
        unload_api(&api);
        return 7;
    }

    RknnInput input;
    memset(&input, 0, sizeof(input));
    input.index = 0;
    input.buf = input_buffer;
    input.size = input_size;
    input.pass_through = 0;
    input.type = RKNN_TENSOR_UINT8;
    input.fmt = RKNN_TENSOR_NHWC;

    uint32_t warmup = config->warmup;
    uint32_t runs = config->runs == 0 ? 1 : config->runs;
    double total_ms = 0.0;
    int status = 0;
    const char *stage = "ok";
    DecodeSummary decode_summary;

    for (uint32_t index = 0; index < warmup + runs; ++index) {
        ret = api.inputs_set(ctx, 1, &input);
        if (ret != RKNN_SUCC) {
            fprintf(stderr, "rknn_inputs_set failed: %d\n", ret);
            status = 8;
            stage = "inputs_set_failed";
            break;
        }
        uint64_t start_us = monotonic_time_us();
        ret = api.run(ctx, nullptr);
        if (ret != RKNN_SUCC) {
            fprintf(stderr, "rknn_run failed: %d\n", ret);
            status = 9;
            stage = "run_failed";
            break;
        }
        RknnOutput *rknn_outputs = static_cast<RknnOutput *>(calloc(io_num.n_output, sizeof(RknnOutput)));
        if (!rknn_outputs) {
            status = 10;
            stage = "output_alloc_failed";
            break;
        }
        for (uint32_t output_index = 0; output_index < io_num.n_output; ++output_index) {
            rknn_outputs[output_index].index = output_index;
            rknn_outputs[output_index].want_float = config->want_float;
            rknn_outputs[output_index].is_prealloc = 0;
        }
        ret = api.outputs_get(ctx, io_num.n_output, rknn_outputs, nullptr);
        uint64_t end_us = monotonic_time_us();
        if (ret != RKNN_SUCC) {
            fprintf(stderr, "rknn_outputs_get failed: %d\n", ret);
            free(rknn_outputs);
            status = 11;
            stage = "outputs_get_failed";
            break;
        }
        if (index >= warmup) {
            total_ms += static_cast<double>(end_us - start_us) / 1000.0;
        }
        if (status == 0 && index + 1 == warmup + runs) {
            decode_summary = decode_rockchip_yolov8_outputs(outputs, rknn_outputs, io_num.n_output);
        }
        api.outputs_release(ctx, io_num.n_output, rknn_outputs);
        free(rknn_outputs);
    }

    double mean_ms = status == 0 ? total_ms / runs : 0.0;
    write_report(config->report_path, config, &version, &io_num, inputs, outputs, status, stage, mean_ms, &decode_summary);

    free(input_buffer);
    free(inputs);
    free(outputs);
    api.destroy(ctx);
    unload_api(&api);
    return status;
}
