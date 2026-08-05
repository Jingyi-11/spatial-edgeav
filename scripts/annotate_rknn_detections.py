#!/usr/bin/env python3
"""Draw RKNN YOLO detections on a PPM/PNG input image.

The dependency-free path supports P6 PPM input and PPM output. If Pillow is
installed, the script can also read/write PNG and other common image formats.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ModuleNotFoundError:  # Keep the default PPM workflow dependency-free.
    Image = None
    ImageDraw = None


COCO80 = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


def class_name(class_id: int) -> str:
    if 0 <= class_id < len(COCO80):
        return COCO80[class_id]
    return f"class_{class_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="Input PPM/PNG image used by RKNN")
    parser.add_argument("--report", required=True, type=Path, help="RKNN JSON report with detections")
    parser.add_argument("--output", required=True, type=Path, help="Annotated PNG output path")
    return parser.parse_args()


def read_ppm(path: Path) -> tuple[int, int, bytearray]:
    data = path.read_bytes()
    tokens: list[bytes] = []
    index = 0
    while len(tokens) < 4:
        while index < len(data) and data[index:index + 1].isspace():
            index += 1
        if index < len(data) and data[index:index + 1] == b"#":
            while index < len(data) and data[index:index + 1] not in (b"\n", b"\r"):
                index += 1
            continue
        start = index
        while index < len(data) and not data[index:index + 1].isspace():
            index += 1
        tokens.append(data[start:index])

    if tokens[0] != b"P6":
        raise ValueError(f"{path} is not a binary P6 PPM image")
    width = int(tokens[1])
    height = int(tokens[2])
    max_value = int(tokens[3])
    if max_value != 255:
        raise ValueError("only 8-bit PPM images are supported")
    while index < len(data) and data[index:index + 1].isspace():
        index += 1
    pixels = bytearray(data[index:])
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(f"PPM payload has {len(pixels)} bytes, expected {expected}")
    return width, height, pixels


def write_ppm(path: Path, width: int, height: int, pixels: bytearray) -> None:
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(pixels))


def put_pixel(pixels: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    offset = (y * width + x) * 3
    pixels[offset:offset + 3] = bytes(color)


def draw_rect_ppm(
    pixels: bytearray,
    width: int,
    height: int,
    xyxy: list[float],
    color: tuple[int, int, int],
    thickness: int = 3,
) -> None:
    x1, y1, x2, y2 = [int(round(value)) for value in xyxy]
    for t in range(thickness):
        for x in range(x1, x2 + 1):
            put_pixel(pixels, width, height, x, y1 + t, color)
            put_pixel(pixels, width, height, x, y2 - t, color)
        for y in range(y1, y2 + 1):
            put_pixel(pixels, width, height, x1 + t, y, color)
            put_pixel(pixels, width, height, x2 - t, y, color)


def annotate_with_ppm(args: argparse.Namespace, detections: list[dict]) -> None:
    if args.image.suffix.lower() != ".ppm" or args.output.suffix.lower() != ".ppm":
        raise RuntimeError("Pillow is not installed; use PPM input and PPM output")
    width, height, pixels = read_ppm(args.image)
    colors = [(0, 255, 102), (255, 204, 0), (0, 170, 255), (255, 102, 204), (255, 102, 51)]
    for index, detection in enumerate(detections):
        draw_rect_ppm(pixels, width, height, detection["bbox_xyxy"], colors[index % len(colors)])
    write_ppm(args.output, width, height, pixels)


def annotate_with_pillow(args: argparse.Namespace, detections: list[dict]) -> None:
    image = Image.open(args.image).convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = ["#00ff66", "#ffcc00", "#00aaff", "#ff66cc", "#ff6633"]

    for index, detection in enumerate(detections):
        x1, y1, x2, y2 = detection["bbox_xyxy"]
        class_id = int(detection["class_id"])
        confidence = float(detection["confidence"])
        label = f"{class_name(class_id)} {confidence:.2f}"
        color = colors[index % len(colors)]

        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        text_y = max(0, y1 - 18)
        text_box = draw.textbbox((x1, text_y), label)
        draw.rectangle(
            [text_box[0] - 2, text_box[1] - 1, text_box[2] + 2, text_box[3] + 1],
            fill=color,
        )
        draw.text((x1, text_y), label, fill="black")
    image.save(args.output)


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text())
    detections = report.get("detections", [])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if Image is None:
        annotate_with_ppm(args, detections)
    else:
        annotate_with_pillow(args, detections)
    print(f"wrote {args.output}")
    print(f"detections={len(detections)}")
    for detection in detections:
        class_id = int(detection["class_id"])
        confidence = float(detection["confidence"])
        print(f"{class_id} {class_name(class_id)} {confidence:.4f} {detection['bbox_xyxy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
