#ifndef RKNN_API_COMPAT_H
#define RKNN_API_COMPAT_H

#include <stdint.h>

#ifdef __arm__
typedef uint32_t rknn_context;
#else
typedef uint64_t rknn_context;
#endif

#define RKNN_SUCC 0
#define RKNN_MAX_DIMS 16
#define RKNN_MAX_NAME_LEN 256

typedef enum RknnQueryCmd {
    RKNN_QUERY_IN_OUT_NUM = 0,
    RKNN_QUERY_INPUT_ATTR = 1,
    RKNN_QUERY_OUTPUT_ATTR = 2,
    RKNN_QUERY_SDK_VERSION = 5,
} RknnQueryCmd;

typedef enum RknnTensorType {
    RKNN_TENSOR_FLOAT32 = 0,
    RKNN_TENSOR_FLOAT16 = 1,
    RKNN_TENSOR_INT8 = 2,
    RKNN_TENSOR_UINT8 = 3,
    RKNN_TENSOR_INT16 = 4,
    RKNN_TENSOR_UINT16 = 5,
    RKNN_TENSOR_INT32 = 6,
    RKNN_TENSOR_UINT32 = 7,
    RKNN_TENSOR_INT64 = 8,
    RKNN_TENSOR_BOOL = 9,
    RKNN_TENSOR_INT4 = 10,
} RknnTensorType;

typedef enum RknnTensorFormat {
    RKNN_TENSOR_NCHW = 0,
    RKNN_TENSOR_NHWC = 1,
    RKNN_TENSOR_NC1HWC2 = 2,
    RKNN_TENSOR_UNDEFINED = 3,
} RknnTensorFormat;

typedef enum RknnTensorQntType {
    RKNN_TENSOR_QNT_NONE = 0,
    RKNN_TENSOR_QNT_DFP = 1,
    RKNN_TENSOR_QNT_AFFINE_ASYMMETRIC = 2,
} RknnTensorQntType;

typedef struct RknnInputOutputNum {
    uint32_t n_input;
    uint32_t n_output;
} RknnInputOutputNum;

typedef struct RknnTensorAttr {
    uint32_t index;
    uint32_t n_dims;
    uint32_t dims[RKNN_MAX_DIMS];
    char name[RKNN_MAX_NAME_LEN];
    uint32_t n_elems;
    uint32_t size;
    RknnTensorFormat fmt;
    RknnTensorType type;
    RknnTensorQntType qnt_type;
    int8_t fl;
    int32_t zp;
    float scale;
    uint32_t w_stride;
    uint32_t size_with_stride;
    uint8_t pass_through;
    uint32_t h_stride;
} RknnTensorAttr;

typedef struct RknnSdkVersion {
    char api_version[256];
    char drv_version[256];
} RknnSdkVersion;

typedef struct RknnInput {
    uint32_t index;
    void *buf;
    uint32_t size;
    uint8_t pass_through;
    RknnTensorType type;
    RknnTensorFormat fmt;
} RknnInput;

typedef struct RknnOutput {
    uint8_t want_float;
    uint8_t is_prealloc;
    uint32_t index;
    void *buf;
    uint32_t size;
} RknnOutput;

typedef struct RknnInitExtend {
    rknn_context ctx;
    int32_t real_model_offset;
    uint32_t real_model_size;
    uint8_t reserved[120];
} RknnInitExtend;

typedef struct RknnRunExtend {
    uint64_t frame_id;
    int32_t non_block;
    int32_t timeout_ms;
    int32_t fence_fd;
} RknnRunExtend;

typedef struct RknnOutputExtend {
    uint64_t frame_id;
} RknnOutputExtend;

#endif
