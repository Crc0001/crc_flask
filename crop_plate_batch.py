#!/usr/bin/env python3
"""Batch-crop Petri dishes while preserving source pixels."""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFile


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class CircleCandidate:
    cx: float
    cy: float
    radius: float
    confidence: float
    method: str


@dataclass(frozen=True)
class CropDetection:
    cx: float
    cy: float
    radius: float
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float
    method: str
    needs_review: bool
    review_reasons: tuple[str, ...]


def _resize_for_detection(image: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = image.shape[:2]
    scale = min(1.0, 800 / float(max(height, width)))
    if scale == 1.0:
        return image, scale
    resized = cv2.resize(
        image,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def _foreground_candidate(image: np.ndarray) -> CircleCandidate | None:
    height, width = image.shape[:2]
    patch = max(12, round(min(height, width) * 0.06))
    corners = np.concatenate(
        [
            image[:patch, :patch].reshape(-1, 3),
            image[:patch, -patch:].reshape(-1, 3),
            image[-patch:, :patch].reshape(-1, 3),
            image[-patch:, -patch:].reshape(-1, 3),
        ]
    ).astype(np.float32)
    background = np.median(corners, axis=0)
    difference = np.linalg.norm(image.astype(np.float32) - background, axis=2)
    difference = np.clip(difference, 0, 255).astype(np.uint8)
    blurred = cv2.GaussianBlur(difference, (9, 9), 0)
    _, mask = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    kernel_size = max(9, round(min(height, width) * 0.025))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_area = float(height * width)
    candidates = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < image_area * 0.12:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if not 0.22 <= radius / min(height, width) <= 0.62:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        circularity = 0.0 if perimeter == 0 else 4.0 * np.pi * area / perimeter**2
        fill_ratio = area / max(np.pi * radius**2, 1.0)
        center_distance = np.hypot(cx - width / 2, cy - height / 2)
        center_score = max(0.0, 1.0 - center_distance / (0.7 * min(height, width)))
        confidence = float(
            np.clip(
                0.45 * min(1.0, fill_ratio / 0.72)
                + 0.30 * min(1.0, circularity / 0.72)
                + 0.25 * center_score,
                0.0,
                1.0,
            )
        )
        candidates.append(CircleCandidate(cx, cy, radius, confidence, "foreground"))
    return max(candidates, key=lambda item: item.confidence, default=None)


def _hough_candidate(image: np.ndarray) -> CircleCandidate | None:
    height, width = image.shape[:2]
    gray = cv2.medianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 9)
    min_dimension = min(height, width)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min_dimension * 0.45,
        param1=120,
        param2=55,
        minRadius=round(min_dimension * 0.24),
        maxRadius=round(min_dimension * 0.58),
    )
    if circles is None:
        return None

    edges = cv2.Canny(gray, 60, 140)
    candidates = []
    for cx, cy, radius in circles[0]:
        angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
        xs = np.rint(cx + radius * np.cos(angles)).astype(int)
        ys = np.rint(cy + radius * np.sin(angles)).astype(int)
        valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        if valid.mean() < 0.90:
            continue
        support = []
        for delta in (-3, 0, 3):
            sample_x = np.clip(xs[valid], 0, width - 1)
            sample_y = np.clip(ys[valid] + delta, 0, height - 1)
            support.append(edges[sample_y, sample_x] > 0)
        edge_support = np.logical_or.reduce(support).mean()
        center_distance = np.hypot(cx - width / 2, cy - height / 2)
        center_score = max(0.0, 1.0 - center_distance / (0.7 * min_dimension))
        confidence = float(
            np.clip(0.65 * edge_support / 0.18 + 0.35 * center_score, 0, 1)
        )
        candidates.append(CircleCandidate(cx, cy, radius, confidence, "hough"))
    return max(candidates, key=lambda item: item.confidence, default=None)


def detect_plate_circle(image: np.ndarray) -> CircleCandidate:
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected a non-empty BGR color image")
    resized, scale = _resize_for_detection(image)
    foreground = _foreground_candidate(resized)
    hough = None if foreground and foreground.confidence >= 0.90 else _hough_candidate(resized)

    if foreground and hough:
        center_gap = np.hypot(foreground.cx - hough.cx, foreground.cy - hough.cy)
        radius_gap = abs(foreground.radius - hough.radius)
        agree = (
            center_gap <= 0.08 * min(resized.shape[:2])
            and radius_gap <= 0.10 * max(foreground.radius, hough.radius)
        )
        if agree:
            total = max(foreground.confidence + hough.confidence, 1e-6)
            selected = CircleCandidate(
                (foreground.cx * foreground.confidence + hough.cx * hough.confidence)
                / total,
                (foreground.cy * foreground.confidence + hough.cy * hough.confidence)
                / total,
                max(foreground.radius, hough.radius),
                min(1.0, 0.15 + 0.5 * (foreground.confidence + hough.confidence)),
                "foreground+hough",
            )
        else:
            best = max((foreground, hough), key=lambda item: item.confidence)
            selected = CircleCandidate(
                best.cx, best.cy, best.radius, best.confidence * 0.82, best.method
            )
    else:
        selected = foreground or hough
    if selected is None:
        raise ValueError("No plausible Petri dish circle detected")
    return CircleCandidate(
        selected.cx / scale,
        selected.cy / scale,
        selected.radius / scale,
        selected.confidence,
        selected.method,
    )


def crop_plate(
    image: np.ndarray,
    padding_ratio: float = 0.015,
    review_threshold: float = 0.65,
) -> tuple[np.ndarray, CropDetection]:
    if not 0.0 <= padding_ratio <= 0.20:
        raise ValueError("padding must be between 0 and 0.20")
    height, width = image.shape[:2]
    candidate = detect_plate_circle(image)
    radius = candidate.radius * (1.0 + padding_ratio)
    x1 = max(0, int(np.floor(candidate.cx - radius)))
    y1 = max(0, int(np.floor(candidate.cy - radius)))
    x2 = min(width, int(np.ceil(candidate.cx + radius)))
    y2 = min(height, int(np.ceil(candidate.cy + radius)))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Detected crop is empty")

    reasons = []
    if candidate.confidence < review_threshold:
        reasons.append("low_confidence")
    if x1 == 0 or y1 == 0 or x2 == width or y2 == height:
        reasons.append("plate_near_image_edge")
    if (x2 - x1) * (y2 - y1) / float(width * height) > 0.95:
        reasons.append("little_background_removed")
    detection = CropDetection(
        candidate.cx,
        candidate.cy,
        candidate.radius,
        x1,
        y1,
        x2,
        y2,
        candidate.confidence,
        candidate.method,
        bool(reasons),
        tuple(reasons),
    )
    return image[y1:y2, x1:x2].copy(), detection


def draw_crop_preview(image: np.ndarray, detection: CropDetection) -> np.ndarray:
    preview = image.copy()
    color = (0, 165, 255) if detection.needs_review else (40, 190, 40)
    thickness = max(3, round(min(image.shape[:2]) / 500))
    cv2.circle(
        preview,
        (round(detection.cx), round(detection.cy)),
        round(detection.radius),
        color,
        thickness,
    )
    cv2.rectangle(
        preview,
        (detection.x1, detection.y1),
        (detection.x2 - 1, detection.y2 - 1),
        color,
        thickness,
    )
    return preview


def read_image(path: Path) -> tuple[np.ndarray, str]:
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is not None:
        return image, "opencv"
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        with Image.open(path) as pil_image:
            rgb = np.asarray(pil_image.convert("RGB"))
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = False
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), "pillow_truncated_fallback"


def write_image(path: Path, image: np.ndarray, extension: str) -> None:
    success, encoded = cv2.imencode(extension, image)
    if not success:
        raise ValueError(f"OpenCV could not encode {extension}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--padding", type=float, default=0.015)
    parser.add_argument("--review-threshold", type=float, default=0.65)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-review-previews", action="store_true")
    parser.add_argument("--output-format", choices=("png", "jpg"), default="png")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    if input_root == output_root or input_root in output_root.parents:
        raise ValueError("Output root must be outside the input root")
    images = sorted(
        (
            path
            for path in input_root.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=lambda path: str(path.relative_to(input_root)).lower(),
    )
    if args.limit is not None:
        images = images[: args.limit]
    if args.sample_size is not None:
        if args.sample_size <= 0:
            raise ValueError("sample-size must be positive")
        images = random.Random(args.seed).sample(
            images, min(args.sample_size, len(images))
        )
        images.sort(key=lambda path: str(path.relative_to(input_root)).lower())
    if not images:
        raise ValueError("No supported images found")

    output_root.mkdir(parents=True, exist_ok=True)
    preview_root = output_root / "_crop_review"
    records = []
    for index, source in enumerate(images, start=1):
        relative = source.relative_to(input_root)
        record = {"source": str(relative), "status": "failed"}
        try:
            image, decoder = read_image(source)
            cropped, detection = crop_plate(
                image,
                padding_ratio=args.padding,
                review_threshold=args.review_threshold,
            )
            output_relative = relative.with_suffix(f".{args.output_format}")
            destination = output_root / output_relative
            if not args.dry_run:
                write_image(destination, cropped, f".{args.output_format}")
            review_reasons = list(detection.review_reasons)
            if decoder != "opencv":
                review_reasons.append(decoder)
            needs_review = bool(review_reasons)
            record.update(
                {
                    "output": str(output_relative),
                    "status": "review" if needs_review else "ok",
                    "method": detection.method,
                    "decoder": decoder,
                    "confidence": f"{detection.confidence:.4f}",
                    "original_width": image.shape[1],
                    "original_height": image.shape[0],
                    "crop_x1": detection.x1,
                    "crop_y1": detection.y1,
                    "crop_x2": detection.x2,
                    "crop_y2": detection.y2,
                    "output_width": cropped.shape[1],
                    "output_height": cropped.shape[0],
                    "review_reasons": "|".join(review_reasons),
                }
            )
            if needs_review and not args.no_review_previews:
                preview = draw_crop_preview(image, detection)
                write_image((preview_root / relative).with_suffix(".jpg"), preview, ".jpg")
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        records.append(record)
        if index % 25 == 0 or index == len(images):
            print(f"Processed {index}/{len(images)}")

    fields = [
        "source",
        "output",
        "status",
        "method",
        "decoder",
        "confidence",
        "original_width",
        "original_height",
        "crop_x1",
        "crop_y1",
        "crop_x2",
        "crop_y2",
        "output_width",
        "output_height",
        "review_reasons",
        "error",
    ]
    with (output_root / "crop_manifest.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    counts = {
        status: sum(record["status"] == status for record in records)
        for status in ("ok", "review", "failed")
    }
    print(f"Completed: {counts}")
    print(f"Manifest: {output_root / 'crop_manifest.csv'}")


if __name__ == "__main__":
    main()
