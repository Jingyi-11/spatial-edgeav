CC ?= cc
BUILD_DIR := build
TARGET := $(BUILD_DIR)/embedded_camera

CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Iinclude
LDFLAGS ?=

SOURCES := src/main.c src/pipeline.c src/camera_capture.c src/yuv.c
OBJECTS := $(SOURCES:src/%.c=$(BUILD_DIR)/%.o)

.PHONY: all clean run-sim probe rk3567-sim edgeav-smoke setup-rknn-wsl export-onnx collect-rknn-calib collect-rknn-calib-board convert-rknn-fp convert-rknn-i8 setup-rknn-converter-board convert-rknn-i8-board setup-rknn-board deploy-rknn-board deploy-rknn-board-i8 compare-rknn-benchmarks

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@

$(BUILD_DIR)/%.o: src/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

out:
	mkdir -p out

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

setup-rknn-board:
	scp scripts/rk3576_setup_rknn_runtime.sh rk3576:/tmp/
	ssh -t rk3576 "bash /tmp/rk3576_setup_rknn_runtime.sh"

deploy-rknn-board:
	bash scripts/deploy_rknn_to_rk3576.sh

deploy-rknn-board-i8:
	bash scripts/deploy_rknn_to_rk3576.sh runs/model_exports/yolov8n/yolov8n_rk3576_i8.rknn

compare-rknn-benchmarks:
	python3 scripts/compare_rknn_benchmarks.py \
	  --fp runs/rk3576_board/yolov8n_rk3576_fp_rk3576_report.json \
	  --i8 runs/rk3576_board/yolov8n_rk3576_i8_rk3576_report.json \
	  --out runs/rk3576_board/fp_vs_i8_comparison.json

clean:
	rm -rf $(BUILD_DIR) out
