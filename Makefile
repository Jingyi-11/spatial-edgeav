CC ?= cc
BUILD_DIR := build
TARGET := $(BUILD_DIR)/embedded_camera

CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Iinclude
LDFLAGS ?=

SOURCES := src/main.c src/pipeline.c src/camera_capture.c src/yuv.c
OBJECTS := $(SOURCES:src/%.c=$(BUILD_DIR)/%.o)

.PHONY: all clean run-sim probe rk3567-sim edgeav-smoke setup-rknn-wsl export-onnx convert-rknn-fp

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

convert-rknn-fp:
	bash scripts/wsl_convert_yolov8_rknn.sh /mnt/c/Users/HP/edgeav_data/exports/yolov8n/yolov8n.onnx fp rk3576

clean:
	rm -rf $(BUILD_DIR) out
