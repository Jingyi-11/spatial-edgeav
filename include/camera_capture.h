#ifndef CAMERA_CAPTURE_H
#define CAMERA_CAPTURE_H

#include "pipeline.h"

typedef struct CameraCapture CameraCapture;

typedef void (*FrameCallback)(const VideoFrame *frame, void *userdata);

int camera_open(CameraCapture **camera, const PipelineConfig *config);
int camera_start(CameraCapture *camera);
int camera_capture_frames(CameraCapture *camera, FrameCallback callback, void *userdata);
void camera_stop(CameraCapture *camera);
void camera_close(CameraCapture *camera);
int camera_probe(const char *device);

#endif
