#include "rknn_detector.h"
#include "rknn_api_compat.h"
#include "pipeline.h"

#include <dlfcn.h>
#include <errno.h>
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
    double inference_mean_ms)
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
        api.outputs_release(ctx, io_num.n_output, rknn_outputs);
        free(rknn_outputs);
    }

    double mean_ms = status == 0 ? total_ms / runs : 0.0;
    write_report(config->report_path, config, &version, &io_num, inputs, outputs, status, stage, mean_ms);

    free(input_buffer);
    free(inputs);
    free(outputs);
    api.destroy(ctx);
    unload_api(&api);
    return status;
}
