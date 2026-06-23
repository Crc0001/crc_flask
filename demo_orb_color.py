#!/usr/bin/env python3
"""
Demo 2 (v2): ORB + HSV color histogram fusion retrieval.

Enhancements:
- center crop to reduce background noise
- CLAHE normalization on grayscale for more stable keypoints
- AKAZE fallback when ORB keypoints are too weak

Usage:
  python demo_orb_color.py --query ./query.jpg --db_dir ./db_images --topk 5
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def list_images(db_dir: Path) -> List[Path]:
    return sorted([p for p in db_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS])


def center_crop(img_bgr: np.ndarray, crop_ratio: float = 0.8) -> np.ndarray:
    crop_ratio = float(np.clip(crop_ratio, 0.3, 1.0))
    if crop_ratio >= 0.999:
        return img_bgr

    h, w = img_bgr.shape[:2]
    ch, cw = int(h * crop_ratio), int(w * crop_ratio)
    y1 = (h - ch) // 2
    x1 = (w - cw) // 2
    return img_bgr[y1:y1 + ch, x1:x1 + cw]


def preprocess(img_bgr: np.ndarray, size: int = 256, crop_ratio: float = 0.8) -> np.ndarray:
    cropped = center_crop(img_bgr, crop_ratio=crop_ratio)
    return cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)


def normalize_gray_for_features(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _ratio_good_matches(des1: np.ndarray, des2: np.ndarray, norm_type: int, ratio: float = 0.75) -> int:
    bf = cv2.BFMatcher(norm_type, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)

    good = 0
    for m_n in matches:
        if len(m_n) < 2:
            continue
        m, n = m_n
        if m.distance < ratio * n.distance:
            good += 1
    return good


def orb_similarity(q_img: np.ndarray, db_img: np.ndarray) -> float:
    gray_q = normalize_gray_for_features(q_img)
    gray_d = normalize_gray_for_features(db_img)

    orb = cv2.ORB_create(nfeatures=1500)
    kp1, des1 = orb.detectAndCompute(gray_q, None)
    kp2, des2 = orb.detectAndCompute(gray_d, None)

    if des1 is not None and des2 is not None and len(kp1) >= 10 and len(kp2) >= 10:
        good = _ratio_good_matches(des1, des2, cv2.NORM_HAMMING, ratio=0.75)
        denom = max(min(len(kp1), len(kp2)), 1)
        return float(np.clip(good / float(denom), 0.0, 1.0))

    # ORB too weak => AKAZE fallback
    akaze = cv2.AKAZE_create()
    kp1, des1 = akaze.detectAndCompute(gray_q, None)
    kp2, des2 = akaze.detectAndCompute(gray_d, None)
    if des1 is None or des2 is None or len(kp1) == 0 or len(kp2) == 0:
        return 0.0

    good = _ratio_good_matches(des1, des2, cv2.NORM_HAMMING, ratio=0.78)
    denom = max(min(len(kp1), len(kp2)), 1)
    return float(np.clip(good / float(denom), 0.0, 1.0))


def color_hist_similarity(q_img: np.ndarray, db_img: np.ndarray) -> float:
    hsv_q = cv2.cvtColor(q_img, cv2.COLOR_BGR2HSV)
    hsv_d = cv2.cvtColor(db_img, cv2.COLOR_BGR2HSV)

    hist_size = [32, 32]
    ranges = [0, 180, 0, 256]
    channels = [0, 1]  # H,S

    hq = cv2.calcHist([hsv_q], channels, None, hist_size, ranges)
    hd = cv2.calcHist([hsv_d], channels, None, hist_size, ranges)
    cv2.normalize(hq, hq, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(hd, hd, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    corr = cv2.compareHist(hq, hd, cv2.HISTCMP_CORREL)  # [-1, 1]
    return float(np.clip((corr + 1.0) / 2.0, 0.0, 1.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="ORB + color fusion image retrieval (v2)")
    parser.add_argument("--query", required=True, help="Query image path")
    parser.add_argument("--db_dir", required=True, help="Directory of candidate images")
    parser.add_argument("--topk", type=int, default=5, help="Top K results")
    parser.add_argument("--w_orb", type=float, default=0.2, help="Weight of ORB/AKAZE score")
    parser.add_argument("--w_color", type=float, default=0.8, help="Weight of color score")
    parser.add_argument("--size", type=int, default=256, help="Resize target (square)")
    parser.add_argument("--crop_ratio", type=float, default=0.8, help="Center crop ratio (0.3~1.0)")
    args = parser.parse_args()

    query_path = Path(args.query)
    db_dir = Path(args.db_dir)

    if not query_path.exists():
        raise FileNotFoundError(f"Query image not found: {query_path}")
    if not db_dir.exists() or not db_dir.is_dir():
        raise NotADirectoryError(f"db_dir is invalid: {db_dir}")

    db_images = list_images(db_dir)
    if not db_images:
        print("No images found in db_dir.")
        return

    w_orb = float(args.w_orb)
    w_color = float(args.w_color)
    weight_sum = w_orb + w_color
    if weight_sum <= 0:
        raise ValueError("w_orb + w_color must be > 0")
    w_orb /= weight_sum
    w_color /= weight_sum

    q_raw = cv2.imread(str(query_path))
    if q_raw is None:
        raise ValueError(f"Failed to read query image: {query_path}")
    q_img = preprocess(q_raw, size=args.size, crop_ratio=args.crop_ratio)

    results: List[Tuple[Path, float, float, float]] = []
    for p in db_images:
        db_raw = cv2.imread(str(p))
        if db_raw is None:
            continue
        db_img = preprocess(db_raw, size=args.size, crop_ratio=args.crop_ratio)

        s_orb = orb_similarity(q_img, db_img)
        s_color = color_hist_similarity(q_img, db_img)
        s_final = w_orb * s_orb + w_color * s_color
        results.append((p, s_final, s_orb, s_color))

    results.sort(key=lambda x: x[1], reverse=True)
    topk = max(1, args.topk)

    print(f"Query: {query_path}")
    print(f"DB dir: {db_dir}")
    print(f"Weights => ORB: {w_orb:.2f}, Color: {w_color:.2f}")
    print(f"Preprocess => size: {args.size}, crop_ratio: {float(args.crop_ratio):.2f}")
    print("=" * 80)
    for rank, (p, final_s, orb_s, color_s) in enumerate(results[:topk], start=1):
        print(
            f"{rank:02d}. {p.name:<30} "
            f"final={final_s * 100:6.2f}%  "
            f"orb={orb_s * 100:6.2f}%  "
            f"color={color_s * 100:6.2f}%"
        )


if __name__ == "__main__":
    main()
