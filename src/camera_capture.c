#define _POSIX_C_SOURCE 200809L

#include "camera_capture.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifdef __linux__
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <linux/videodev2.h>
#endif

typedef struct CameraBuffer {
    void *start;
    size_t length;
} CameraBuffer;

struct CameraCapture {
    PipelineConfig config;
    int fd;
    CameraBuffer *buffers;
    uint32_t buffer_count;
    uint64_t sequence;
};

#ifdef __linux__
static uint32_t v4l2_format(PixelFormat format)
{
    switch (format) {
    case PIXEL_FORMAT_NV12:
        return V4L2_PIX_FMT_NV12;
    case PIXEL_FORMAT_MJPEG:
        return V4L2_PIX_FMT_MJPEG;
    case PIXEL_FORMAT_YUYV:
    default:
        return V4L2_PIX_FMT_YUYV;
    }
}

static int xioctl(int fd, unsigned long request, void *argument)
{
    int result;
    do {
        result = ioctl(fd, request, argument);
    } while (result == -1 && errno == EINTR);
    return result;
}
#else
static size_t simulated_frame_size(const PipelineConfig *config)
{
    if (config->pixel_format == PIXEL_FORMAT_NV12) {
        return (size_t)config->width * (size_t)config->height * 3u / 2u;
    }
    return (size_t)config->width * (size_t)config->height * 2u;
}

static void fill_simulated_yuyv(uint8_t *data, const PipelineConfig *config, uint64_t sequence)
{
    for (uint32_t y = 0; y < config->height; y++) {
        for (uint32_t x = 0; x < config->width; x += 2) {
            size_t offset = ((size_t)y * config->width + x) * 2u;
            uint8_t luma0 = (uint8_t)((x + sequence * 7u) % 256u);
            uint8_t luma1 = (uint8_t)((y + sequence * 5u) % 256u);
            data[offset + 0] = luma0;
            data[offset + 1] = 128;
            data[offset + 2] = luma1;
            data[offset + 3] = 128;
        }
    }
}
#endif

int camera_open(CameraCapture **camera, const PipelineConfig *config)
{
    if (!camera || !config) {
        return -1;
    }

    CameraCapture *capture = calloc(1, sizeof(*capture));
    if (!capture) {
        return -1;
    }

    capture->config = *config;
    capture->fd = -1;

#ifdef __linux__
    capture->fd = open(config->video_device, O_RDWR | O_NONBLOCK, 0);
    if (capture->fd == -1) {
        perror("open video device");
        free(capture);
        return -1;
    }

    struct v4l2_capability capability;
    memset(&capability, 0, sizeof(capability));
    if (xioctl(capture->fd, VIDIOC_QUERYCAP, &capability) == -1) {
        perror("VIDIOC_QUERYCAP");
        camera_close(capture);
        return -1;
    }

    if (!(capability.capabilities & V4L2_CAP_VIDEO_CAPTURE) || !(capability.capabilities & V4L2_CAP_STREAMING)) {
        fprintf(stderr, "%s does not support video capture streaming\n", config->video_device);
        camera_close(capture);
        return -1;
    }

    struct v4l2_format format;
    memset(&format, 0, sizeof(format));
    format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    format.fmt.pix.width = config->width;
    format.fmt.pix.height = config->height;
    format.fmt.pix.pixelformat = v4l2_format(config->pixel_format);
    format.fmt.pix.field = V4L2_FIELD_ANY;

    if (xioctl(capture->fd, VIDIOC_S_FMT, &format) == -1) {
        perror("VIDIOC_S_FMT");
        camera_close(capture);
        return -1;
    }

    struct v4l2_streamparm parameters;
    memset(&parameters, 0, sizeof(parameters));
    parameters.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parameters.parm.capture.timeperframe.numerator = 1;
    parameters.parm.capture.timeperframe.denominator = config->fps;
    xioctl(capture->fd, VIDIOC_S_PARM, &parameters);

    struct v4l2_requestbuffers request;
    memset(&request, 0, sizeof(request));
    request.count = 4;
    request.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    request.memory = V4L2_MEMORY_MMAP;

    if (xioctl(capture->fd, VIDIOC_REQBUFS, &request) == -1) {
        perror("VIDIOC_REQBUFS");
        camera_close(capture);
        return -1;
    }

    capture->buffers = calloc(request.count, sizeof(*capture->buffers));
    if (!capture->buffers) {
        camera_close(capture);
        return -1;
    }
    capture->buffer_count = request.count;

    for (uint32_t index = 0; index < request.count; index++) {
        struct v4l2_buffer buffer;
        memset(&buffer, 0, sizeof(buffer));
        buffer.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buffer.memory = V4L2_MEMORY_MMAP;
        buffer.index = index;

        if (xioctl(capture->fd, VIDIOC_QUERYBUF, &buffer) == -1) {
            perror("VIDIOC_QUERYBUF");
            camera_close(capture);
            return -1;
        }

        capture->buffers[index].length = buffer.length;
        capture->buffers[index].start = mmap(NULL, buffer.length, PROT_READ | PROT_WRITE, MAP_SHARED, capture->fd, buffer.m.offset);
        if (capture->buffers[index].start == MAP_FAILED) {
            perror("mmap");
            camera_close(capture);
            return -1;
        }
    }
#endif

    *camera = capture;
    return 0;
}

int camera_start(CameraCapture *camera)
{
    if (!camera) {
        return -1;
    }

#ifdef __linux__
    for (uint32_t index = 0; index < camera->buffer_count; index++) {
        struct v4l2_buffer buffer;
        memset(&buffer, 0, sizeof(buffer));
        buffer.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buffer.memory = V4L2_MEMORY_MMAP;
        buffer.index = index;
        if (xioctl(camera->fd, VIDIOC_QBUF, &buffer) == -1) {
            perror("VIDIOC_QBUF");
            return -1;
        }
    }

    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(camera->fd, VIDIOC_STREAMON, &type) == -1) {
        perror("VIDIOC_STREAMON");
        return -1;
    }
#endif

    return 0;
}

int camera_capture_frames(CameraCapture *camera, FrameCallback callback, void *userdata)
{
    if (!camera || !callback) {
        return -1;
    }

#ifdef __linux__
    for (uint32_t captured = 0; captured < camera->config.frames; captured++) {
        fd_set descriptors;
        struct timeval timeout;
        FD_ZERO(&descriptors);
        FD_SET(camera->fd, &descriptors);
        timeout.tv_sec = 2;
        timeout.tv_usec = 0;

        int ready = select(camera->fd + 1, &descriptors, NULL, NULL, &timeout);
        if (ready == -1) {
            if (errno == EINTR) {
                captured--;
                continue;
            }
            perror("select");
            return -1;
        }
        if (ready == 0) {
            fprintf(stderr, "camera capture timeout\n");
            return -1;
        }

        struct v4l2_buffer buffer;
        memset(&buffer, 0, sizeof(buffer));
        buffer.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buffer.memory = V4L2_MEMORY_MMAP;

        if (xioctl(camera->fd, VIDIOC_DQBUF, &buffer) == -1) {
            if (errno == EAGAIN) {
                captured--;
                continue;
            }
            perror("VIDIOC_DQBUF");
            return -1;
        }

        VideoFrame frame = {
            .data = camera->buffers[buffer.index].start,
            .size = buffer.bytesused,
            .width = camera->config.width,
            .height = camera->config.height,
            .pixel_format = camera->config.pixel_format,
            .timestamp_us = monotonic_time_us(),
            .sequence = camera->sequence++,
        };
        callback(&frame, userdata);

        if (xioctl(camera->fd, VIDIOC_QBUF, &buffer) == -1) {
            perror("VIDIOC_QBUF");
            return -1;
        }
    }
#else
    size_t frame_size = simulated_frame_size(&camera->config);
    uint8_t *data = malloc(frame_size);
    if (!data) {
        return -1;
    }

    for (uint32_t captured = 0; captured < camera->config.frames; captured++) {
        fill_simulated_yuyv(data, &camera->config, camera->sequence);
        VideoFrame frame = {
            .data = data,
            .size = frame_size,
            .width = camera->config.width,
            .height = camera->config.height,
            .pixel_format = PIXEL_FORMAT_YUYV,
            .timestamp_us = monotonic_time_us(),
            .sequence = camera->sequence++,
        };
        callback(&frame, userdata);
        usleep(1000000u / camera->config.fps);
    }

    free(data);
#endif

    return 0;
}

void camera_stop(CameraCapture *camera)
{
    if (!camera) {
        return;
    }

#ifdef __linux__
    if (camera->fd != -1) {
        enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        xioctl(camera->fd, VIDIOC_STREAMOFF, &type);
    }
#endif
}

void camera_close(CameraCapture *camera)
{
    if (!camera) {
        return;
    }

#ifdef __linux__
    if (camera->buffers) {
        for (uint32_t index = 0; index < camera->buffer_count; index++) {
            if (camera->buffers[index].start && camera->buffers[index].start != MAP_FAILED) {
                munmap(camera->buffers[index].start, camera->buffers[index].length);
            }
        }
        free(camera->buffers);
    }

    if (camera->fd != -1) {
        close(camera->fd);
    }
#endif

    free(camera);
}

int camera_probe(const char *device)
{
#ifdef __linux__
    int fd = open(device, O_RDWR | O_NONBLOCK, 0);
    if (fd == -1) {
        perror("open video device");
        return -1;
    }

    struct v4l2_capability capability;
    memset(&capability, 0, sizeof(capability));
    if (xioctl(fd, VIDIOC_QUERYCAP, &capability) == -1) {
        perror("VIDIOC_QUERYCAP");
        close(fd);
        return -1;
    }

    printf("Driver: %s\n", capability.driver);
    printf("Card: %s\n", capability.card);
    printf("Bus: %s\n", capability.bus_info);

    struct v4l2_fmtdesc format;
    memset(&format, 0, sizeof(format));
    format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

    puts("Formats:");
    while (xioctl(fd, VIDIOC_ENUM_FMT, &format) == 0) {
        printf("  [%u] %s\n", format.index, format.description);
        format.index++;
    }

    close(fd);
    return 0;
#else
    printf("Non-Linux host detected. Probe is simulated for %s.\n", device);
    printf("Formats:\n  [0] YUYV 640x480 synthetic test pattern\n");
    return 0;
#endif
}
