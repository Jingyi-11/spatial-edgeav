# RK3567 Pipeline Walkthrough

这份文档解释当前项目如何被改成 **RK3567 专用学习项目**，以及每个文件在真实嵌入式 Camera pipeline 里扮演什么角色。

## Step 1：项目定位改为 RK3567

原始目标是通用 Linux Camera pipeline。现在改为：

```text
RK3567 Camera + Audio + Vision + AI Inference + RTSP
```

典型链路：

```text
MIPI CSI Sensor
  → rkcif
  → rkisp
  → V4L2 /dev/videoX
  → NV12 frame
  → RGA resize/convert
  → RKNN inference
  → MPP H.264 encode
  → RTSP/WebRTC/MP4
```

USB Camera 链路：

```text
USB Camera
  → uvcvideo
  → V4L2 /dev/videoX
  → YUYV/MJPEG/NV12
  → encode/preview/AI
```

## Step 2：保留 V4L2 MMAP 核心

文件：

```text
src/camera_capture.c
include/camera_capture.h
```

保留原因：

- RK3567 上不管是 USB camera 还是 MIPI camera，应用层最终大概率还是从 V4L2 节点取帧。
- MIPI CSI 复杂在 media graph 和 sensor/ISP 配置，但取帧本身仍然绕不开 V4L2。

当前 C 程序做的事：

1. 打开 `/dev/videoX`
2. `VIDIOC_QUERYCAP`
3. `VIDIOC_S_FMT`
4. `VIDIOC_S_PARM`
5. `VIDIOC_REQBUFS`
6. `VIDIOC_QUERYBUF`
7. `mmap`
8. `VIDIOC_QBUF`
9. `VIDIOC_STREAMON`
10. `select`
11. `VIDIOC_DQBUF`
12. 写 raw frame
13. `VIDIOC_QBUF`
14. `VIDIOC_STREAMOFF`

这就是 RK3567 camera 数据进入用户态的最小路径。

## Step 3：默认格式改为 NV12

文件：

```text
configs/camera.conf
scripts/02_rk3567_capture_nv12.sh
```

为什么是 NV12：

- RK ISP、MPP、很多硬件编码器更喜欢 NV12。
- NV12 是 4:2:0 半平面格式，适合 H.264/H.265 编码。
- 从 camera 到 encoder 尽量使用 NV12，可以减少格式转换成本。

注意：

- USB camera 可能默认输出 YUYV 或 MJPEG。
- MIPI camera 经 rkisp 输出时更常见 NV12/YUYV 等 raw video formats。
- 具体以 `v4l2-ctl --list-formats-ext` 为准。

## Step 4：新增 RK3567 探测脚本

文件：

```text
scripts/01_rk3567_probe_media.sh
```

它做了什么：

- 打印 kernel 信息。
- 列出 `/dev/video*`、`/dev/media*`、`/dev/v4l-subdev*`。
- 调用 `v4l2-ctl --list-devices`。
- 对每个 `/dev/media*` 调用 `media-ctl -p`。
- 对指定 `/dev/videoX` 查看格式、controls、完整能力。
- 检测 `mpph264enc`、`v4l2h264enc`、`x264enc`。

为什么重要：

RK3567 MIPI camera 经常不是单个 `/dev/video0` 就能解释清楚，而是一张 media graph：

```text
sensor subdev → csi/rkcif → isp/rkisp → capture video node
```

你必须先看清楚这张图，后面采集才不会瞎试。

## Step 5：新增 RK3567 NV12 采集脚本

文件：

```text
scripts/02_rk3567_capture_nv12.sh
```

它调用：

```bash
./build/embedded_camera capture --format NV12
```

输出：

```text
out/rk3567_capture_nv12.yuv
```

播放：

```bash
ffplay -f rawvideo -pixel_format nv12 -video_size 1280x720 -framerate 30 out/rk3567_capture_nv12.yuv
```

这个步骤验证：

- V4L2 节点选对了。
- 分辨率/FPS/format 选对了。
- 用户态能稳定拿到 frame。

## Step 6：新增 RK3567 GStreamer 预览

文件：

```text
scripts/07_rk3567_gst_preview_nv12.sh
```

核心 pipeline：

```text
v4l2src
  → video/x-raw,format=NV12
  → videoconvert
  → autovideosink
```

它用来验证：

- camera 实时输出是否正常。
- 图像方向、颜色、帧率是否正常。
- V4L2 caps 是否和 GStreamer 协商成功。

## Step 7：新增 RK3567 MPP/RTSP 推流

文件：

```text
scripts/08_rk3567_gst_rtsp_mpp.sh
```

目标 pipeline：

```text
v4l2src
  → NV12
  → mpph264enc / v4l2h264enc / x264enc
  → h264parse
  → rtspclientsink
```

脚本选择顺序：

1. `mpph264enc`：Rockchip MPP GStreamer 插件。
2. `v4l2h264enc`：如果系统暴露 V4L2 mem2mem encoder。
3. `x264enc`：软件编码 fallback。

为什么这样写：

不同 RK3567 板厂镜像的插件名字和可用性不完全一致。先探测再选择，比硬编码某一个插件更稳。

## Step 8：新增 RK3567 音视频录制脚本

文件：

```text
scripts/09_rk3567_ffmpeg_record_nv12.sh
```

核心：

```text
V4L2 NV12 video + ALSA PCM audio
  → H.264 + AAC
  → MP4
```

这一步用于学习：

- video frame rate
- audio sample rate
- audio/video timestamp
- muxing

当前脚本用 FFmpeg 软件编码，目的是先把音视频容器链路跑通。后续再替换成 MPP 硬编码。

## Step 9：新增 RKNN 部署提示脚本

文件：

```text
scripts/10_rk3567_rknn_notes.sh
```

它不是执行推理，而是列出 RKNN 部署检查清单：

- 板端 runtime 是否存在。
- PC 端用 `rknn-toolkit2` 转模型。
- Camera frame 如何进入 RKNN。
- 相关官方仓库。

下一步真正编码时，可以新增：

```text
src/rknn_infer.c
src/rga_resize.c
src/overlay.c
```

## Step 10：当前项目边界

已经完成：

- RK3567 项目定位
- V4L2 capture C skeleton
- NV12/YUYV raw dump
- RK3567 media graph probe
- RK3567 GStreamer preview
- RK3567 MPP/GStreamer RTSP publish skeleton
- RK3567 FFmpeg audio/video recording script

还未完成：

- 直接调用 MPP C API 编码。
- 直接调用 RKNN C API 推理。
- 直接调用 RGA 做 resize/format convert。
- C/C++ RTSP server。
- 真正的 audio/video PTS sync muxer。

推荐下一步：

1. 在 RK3567 板子上跑 `scripts/01_rk3567_probe_media.sh`。
2. 找到正确 `/dev/videoX` 后跑 `scripts/02_rk3567_capture_nv12.sh`。
3. 跑 `scripts/07_rk3567_gst_preview_nv12.sh`。
4. 装 MediaMTX 后跑 `scripts/08_rk3567_gst_rtsp_mpp.sh`。
5. 把命令输出贴回来，我再按你的板厂镜像具体插件，把 C 代码继续推进到 MPP/RKNN。
