#!/usr/bin/env python3
"""
Demo 1: pHash baseline image retrieval (query vs folder images).

Usage:
  python demo_phash.py --query ./query.jpg --db_dir ./db_images --topk 5
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


def compute_phash(img_bgr: np.ndarray, hash_size: int = 8, highfreq_factor: int = 4) -> np.ndarray:
    size = hash_size * highfreq_factor  # default: 32
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(resized))
    low_freq = dct[:hash_size, :hash_size]

    # 跳过DC分量后取中位数
    flat = low_freq.flatten()
    median = np.median(flat[1:]) if flat.size > 1 else flat[0]
    bits = (low_freq > median).astype(np.uint8)
    return bits


def hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def similarity_from_hamming(dist: int, total_bits: int) -> float:
    return max(0.0, 1.0 - dist / float(total_bits))


def main() -> None:
    parser = argparse.ArgumentParser(description="pHash baseline image retrieval")
    parser.add_argument("--query", required=True, help="Query image path")
    parser.add_argument("--db_dir", required=True, help="Directory of candidate images")
    parser.add_argument("--topk", type=int, default=5, help="Top K results")
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

    q_img = cv2.imread(str(query_path))
    if q_img is None:
        raise ValueError(f"Failed to read query image: {query_path}")
    q_hash = compute_phash(q_img)
    total_bits = q_hash.size

    results: List[Tuple[Path, float, int]] = []
    for p in db_images:
        img = cv2.imread(str(p))
        if img is None:
            continue
        db_hash = compute_phash(img)
        dist = hamming_distance(q_hash, db_hash)
        sim = similarity_from_hamming(dist, total_bits)
        results.append((p, sim, dist))

    results.sort(key=lambda x: x[1], reverse=True)
    topk = max(1, args.topk)

    print(f"Query: {query_path}")
    print(f"DB dir: {db_dir}")
    print("=" * 60)
    for rank, (p, sim, dist) in enumerate(results[:topk], start=1):
        print(f"{rank:02d}. {p.name:<30} similarity={sim * 100:6.2f}%  hamming={dist}")


if __name__ == "__main__":
    main()
