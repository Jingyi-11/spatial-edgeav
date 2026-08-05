CC ?= cc
CXX ?= c++
BUILD_DIR := build
TARGET := $(BUILD_DIR)/embedded_camera
EDGEAV_RUNTIME_TARGET := $(BUILD_DIR)/edgeav_runtime

CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Iinclude
CXXFLAGS ?= -O2 -g
CXXFLAGS += -std=c++17 -Wall -Wextra -Wpedantic -Iinclude
LDFLAGS ?=
LDFLAGS += -pthread
JPEG ?= 0

SOURCES := src/main.c src/pipeline.c src/camera_capture.c src/yuv.c
OBJECTS := $(SOURCES:src/%.c=$(BUILD_DIR)/%.o)
RUNTIME_C_OBJECTS := $(BUILD_DIR)/pipeline.o $(BUILD_DIR)/camera_capture.o $(BUILD_DIR)/yuv.o
RUNTIME_CPP_OBJECTS := $(BUILD_DIR)/edgeav_runtime.o $(BUILD_DIR)/rknn_detector.o

ifeq ($(JPEG),1)
CXXFLAGS += -DEDGEAV_ENABLE_LIBJPEG
RUNTIME_CPP_OBJECTS += $(BUILD_DIR)/jpeg_decode.o
LDFLAGS += -ljpeg
endif

.PHONY: all clean run-sim probe rk3567-sim edgeav-runtime run-edgeav-runtime-sim deploy-cpp-runtime-board probe-media-accel-board run-cpp-capture-yuyv-board run-cpp-capture-mjpeg-board run-cpp-live-yuyv-board run-cpp-continuous-yuyv-board run-cpp-latest-yuyv-board run-cpp-latest-mjpeg-board run-cpp-latest-mjpeg-letterbox-board annotate-cpp-live-yuyv annotate-cpp-continuous-yuyv annotate-cpp-latest-yuyv annotate-cpp-latest-mjpeg annotate-cpp-latest-mjpeg-letterbox edgeav-smoke setup-rknn-wsl export-onnx download-rockchip-yolov8n collect-rknn-calib collect-rknn-calib-board convert-rknn-fp convert-rknn-i8 setup-rknn-converter-board convert-rknn-i8-board convert-rockchip-yolov8n-i8-board setup-rknn-board deploy-rknn-board deploy-rknn-board-i8 deploy-rockchip-yolov8n-i8-board deploy-onnx-cpu-board deploy-rknn-service-board install-rknn-health-timer-board collect-rknn-service-snapshot profile-rknn-service check-rknn-service-health run-rknn-camera-board evaluate-rknn-camera-events benchmark-matrix compare-rknn-benchmarks compare-rknn-detections compare-rockchip-i8-detections

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@

$(BUILD_DIR)/%.o: src/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/%.o: src/%.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

out:
	mkdir -p out

edgeav-runtime: $(EDGEAV_RUNTIME_TARGET)

$(EDGEAV_RUNTIME_TARGET): $(RUNTIME_C_OBJECTS) $(RUNTIME_CPP_OBJECTS)
	$(CXX) $(RUNTIME_C_OBJECTS) $(RUNTIME_CPP_OBJECTS) $(LDFLAGS) -ldl -o $@

run-edgeav-runtime-sim: $(EDGEAV_RUNTIME_TARGET) out
	$(EDGEAV_RUNTIME_TARGET) --simulate --width 1280 --height 720 --fps 30 --frames 30 --format MJPEG --report out/edgeav_runtime_report.json --heartbeat out/edgeav_runtime_heartbeat.json

deploy-cpp-runtime-board:
	bash scripts/deploy_cpp_runtime_to_rk3576.sh

probe-media-accel-board:
	bash scripts/rk3576_probe_media_accel.sh

run-cpp-capture-yuyv-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 120 --format YUYV --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_yuyv_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_yuyv_heartbeat.json"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_yuyv_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_yuyv_heartbeat.json runs/rk3576_cpp_runtime/

run-cpp-capture-mjpeg-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 120 --format MJPEG --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_mjpeg_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_mjpeg_heartbeat.json"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_mjpeg_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_capture_mjpeg_heartbeat.json runs/rk3576_cpp_runtime/

run-cpp-live-yuyv-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 3 --format YUYV --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_heartbeat.json --rknn-model /home/kickpi/spatial-edgeav/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn --rknn-report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_rknn_report.json --rknn-input-dump /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_input.ppm --rknn-runs 3 --rknn-warmup 1"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_heartbeat.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_rknn_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_live_yuyv_input.ppm runs/rk3576_cpp_runtime/

run-cpp-continuous-yuyv-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 30 --format YUYV --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_heartbeat.json --frames-json /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_frames.json --rknn-model /home/kickpi/spatial-edgeav/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn --rknn-input-dump /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_input.ppm --rknn-every-frame"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_heartbeat.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_frames.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_continuous_yuyv_input.ppm runs/rk3576_cpp_runtime/

run-cpp-latest-yuyv-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 30 --format YUYV --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_heartbeat.json --frames-json /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_frames.json --rknn-model /home/kickpi/spatial-edgeav/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn --rknn-input-dump /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_input.ppm --rknn-latest-frame"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_heartbeat.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_frames.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_yuyv_input.ppm runs/rk3576_cpp_runtime/

run-cpp-latest-mjpeg-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 30 --format MJPEG --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_heartbeat.json --frames-json /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_frames.json --rknn-model /home/kickpi/spatial-edgeav/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn --rknn-input-dump /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_input.ppm --rknn-latest-frame"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_heartbeat.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_frames.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_input.ppm runs/rk3576_cpp_runtime/

run-cpp-latest-mjpeg-letterbox-board:
	mkdir -p runs/rk3576_cpp_runtime
	ssh rk3576 "cd /home/kickpi/spatial-edgeav/cpp_runtime_src && ./build/edgeav_runtime --device /dev/video73 --width 1280 --height 720 --fps 30 --frames 30 --format MJPEG --letterbox --report /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_report.json --heartbeat /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_heartbeat.json --frames-json /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_frames.json --rknn-model /home/kickpi/spatial-edgeav/models/yolov8n/yolov8n_rockchip_rk3576_i8.rknn --rknn-input-dump /home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_input.ppm --rknn-latest-frame"
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_report.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_heartbeat.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_frames.json runs/rk3576_cpp_runtime/
	scp rk3576:/home/kickpi/spatial-edgeav/runs/cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_input.ppm runs/rk3576_cpp_runtime/

annotate-cpp-live-yuyv:
	python3 scripts/annotate_rknn_detections.py --image runs/rk3576_cpp_runtime/edgeav_runtime_live_yuyv_input.ppm --report runs/rk3576_cpp_runtime/edgeav_runtime_live_yuyv_rknn_report.json --output runs/rk3576_cpp_runtime/edgeav_runtime_live_yuyv_annotated.ppm

annotate-cpp-continuous-yuyv:
	python3 scripts/annotate_rknn_detections.py --image runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_input.ppm --report runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_frames.json --output runs/rk3576_cpp_runtime/edgeav_runtime_continuous_yuyv_annotated.ppm

annotate-cpp-latest-yuyv:
	python3 scripts/annotate_rknn_detections.py --image runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_input.ppm --report runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_frames.json --output runs/rk3576_cpp_runtime/edgeav_runtime_latest_yuyv_annotated.ppm

annotate-cpp-latest-mjpeg:
	python3 scripts/annotate_rknn_detections.py --image runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_input.ppm --report runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_frames.json --output runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_annotated.ppm

annotate-cpp-latest-mjpeg-letterbox:
	python3 scripts/annotate_rknn_detections.py --image runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_input.ppm --report runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_frames.json --output runs/rk3576_cpp_runtime/edgeav_runtime_latest_mjpeg_letterbox_annotated.ppm

run-sim: $(TARGET) out
	$(TARGET) capture --frames 30 --output out/simulated.yuv --preview out/preview.ppm

rk3567-sim: $(TARGET) out
	$(TARGET) capture --width 1280 --height 720 --fps 30 --frames 30 --format YUYV --output out/rk3567_simulated_yuyv.yuv --preview out/rk3567_preview.ppm

probe: $(TARGET)
	$(TARGET) probe --device /dev/video0

edgeav-smoke:
	bash scripts/run_remote_yolo_pipeline.sh

setup-rknn-wsl:
	bash scripts/wsl_setup_rknn_toolkit2.sh

export-onnx:
	bash scripts/wsl_export_yolov8_onnx.sh

download-rockchip-yolov8n:
	bash scripts/download_rockchip_yolov8n_onnx.sh

collect-rknn-calib:
	bash scripts/collect_rknn_calibration_frames.sh

collect-rknn-calib-board:
	bash scripts/rk3576_collect_calibration_frames.sh rk3576 /dev/video73 100 1280 720 10

convert-rknn-fp:
	bash scripts/wsl_convert_yolov8_rknn.sh /mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx fp rk3576

convert-rknn-i8:
	bash scripts/wsl_convert_yolov8_rknn.sh /mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx i8 rk3576

setup-rknn-converter-board:
	scp scripts/rk3576_setup_rknn_converter.sh rk3576:/tmp/
	ssh rk3576 "bash /tmp/rk3576_setup_rknn_converter.sh"

convert-rknn-i8-board:
	bash scripts/rk3576_convert_yolov8_rknn.sh runs/model_exports/yolov8n/yolov8n.onnx i8 rk3576

convert-rockchip-yolov8n-i8-board:
	bash scripts/rk3576_convert_yolov8_rknn.sh runs/model_exports/rockchip_yolov8n/yolov8n_rockchip.onnx i8 rk3576 runs/model_exports/rockchip_yolov8n

setup-rknn-board:
	scp scripts/rk3576_setup_rknn_runtime.sh rk3576:/tmp/
	ssh -t rk3576 "bash /tmp/rk3576_setup_rknn_runtime.sh"

deploy-rknn-board:
	bash scripts/deploy_rknn_to_rk3576.sh

deploy-rknn-board-i8:
	bash scripts/deploy_rknn_to_rk3576.sh runs/model_exports/yolov8n/yolov8n_rk3576_i8.rknn

deploy-rockchip-yolov8n-i8-board:
	bash scripts/deploy_rknn_to_rk3576.sh runs/model_exports/rockchip_yolov8n/yolov8n_rockchip_rk3576_i8.rknn

deploy-onnx-cpu-board:
	bash scripts/deploy_onnx_cpu_to_rk3576.sh runs/model_exports/yolov8n/yolov8n.onnx

deploy-rknn-service-board:
	bash scripts/deploy_rknn_service_to_rk3576.sh runs/model_exports/rockchip_yolov8n/yolov8n_rockchip_rk3576_i8.rknn

install-rknn-health-timer-board:
	ssh -t rk3576 "INSTALL_HEALTH_TIMER=1 ENABLE_HEALTH_TIMER=1 START_HEALTH_TIMER=1 bash /home/kickpi/spatial-edgeav/bin/rk3576_install_rknn_service.sh"

collect-rknn-service-snapshot:
	bash scripts/collect_rknn_service_snapshot.sh

profile-rknn-service:
	python3 scripts/profile_rknn_service.py --duration-sec 300 --interval-sec 30

check-rknn-service-health:
	python3 scripts/check_rknn_service_health.py

run-rknn-camera-board:
	bash scripts/run_rknn_camera_loop_on_rk3576.sh runs/model_exports/rockchip_yolov8n/yolov8n_rockchip_rk3576_i8.rknn /dev/video73 60

evaluate-rknn-camera-events:
	python3 scripts/evaluate_spatial_rules_jsonl.py \
	  --frames runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_camera_frames.json \
	  --report runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_camera_report.json \
	  --rules configs/spatial_rules.json \
	  --observations-jsonl runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_observations.jsonl \
	  --events-jsonl runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_events.jsonl \
	  --summary runs/rk3576_camera_rknn/yolov8n_rockchip_rk3576_i8_event_summary.json

benchmark-matrix:
	python3 scripts/build_benchmark_matrix.py

compare-rknn-benchmarks:
	python3 scripts/compare_rknn_benchmarks.py \
	  --fp runs/rk3576_board/yolov8n_rk3576_fp_rk3576_report.json \
	  --i8 runs/rk3576_board/yolov8n_rk3576_i8_rk3576_report.json \
	  --out runs/rk3576_board/fp_vs_i8_comparison.json

compare-rknn-detections:
	python3 scripts/compare_rknn_detections.py \
	  --fp runs/rk3576_board/yolov8n_rk3576_fp_detections.json \
	  --i8 runs/rk3576_board/yolov8n_rk3576_i8_detections.json \
	  --out runs/rk3576_board/fp_vs_i8_detections.json

compare-rockchip-i8-detections:
	python3 scripts/compare_rknn_detections.py \
	  --fp runs/rk3576_board/yolov8n_rk3576_fp_detections.json \
	  --i8 runs/rk3576_board/yolov8n_rockchip_rk3576_i8_detections.json \
	  --out runs/rk3576_board/fp_vs_rockchip_i8_detections.json

clean:
	rm -rf $(BUILD_DIR) out
