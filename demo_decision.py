#!/usr/bin/env python3
"""
Demo 3: retrieval + simple decision rule.

It reuses demo_orb_color.py pipeline and adds:
- final decision (Top1 / uncertain)
- Top-K candidate output

Usage:
  python demo_decision.py --query ./query.jpg --db_dir ./db_images --topk 3
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import cv2

from demo_orb_color import list_images, preprocess, orb_similarity, color_hist_similarity


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision demo based on ORB+color retrieval")
    parser.add_argument("--query", required=True, help="Query image path")
    parser.add_argument("--db_dir", required=True, help="Directory of candidate images")
    parser.add_argument("--topk", type=int, default=3, help="Top K candidates to display")

    parser.add_argument("--w_orb", type=float, default=0.2, help="Weight of ORB/AKAZE score")
    parser.add_argument("--w_color", type=float, default=0.8, help="Weight of color score")
    parser.add_argument("--size", type=int, default=256, help="Resize target (square)")
    parser.add_argument("--crop_ratio", type=float, default=0.8, help="Center crop ratio (0.3~1.0)")

    parser.add_argument("--min_top1", type=float, default=0.65, help="Min top1 score to accept")
    parser.add_argument("--min_gap", type=float, default=0.10, help="Min (top1-top2) gap to accept")
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
    s = w_orb + w_color
    if s <= 0:
        raise ValueError("w_orb + w_color must be > 0")
    w_orb /= s
    w_color /= s

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

    if not results:
        print("No valid images could be read from db_dir.")
        return

    results.sort(key=lambda x: x[1], reverse=True)
    topk = max(1, int(args.topk))

    top1 = results[0]
    top2_score = results[1][1] if len(results) > 1 else 0.0
    gap = top1[1] - top2_score

    accepted = (top1[1] >= float(args.min_top1)) and (gap >= float(args.min_gap))

    print(f"Query: {query_path}")
    print(f"DB dir: {db_dir}")
    print(f"Weights => ORB: {w_orb:.2f}, Color: {w_color:.2f}")
    print(f"Preprocess => size: {args.size}, crop_ratio: {float(args.crop_ratio):.2f}")
    print(f"Rule => min_top1: {float(args.min_top1):.2f}, min_gap: {float(args.min_gap):.2f}")
    print("=" * 80)

    for rank, (p, final_s, orb_s, color_s) in enumerate(results[:topk], start=1):
        print(
            f"{rank:02d}. {p.name:<30} "
            f"final={final_s * 100:6.2f}%  "
            f"orb={orb_s * 100:6.2f}%  "
            f"color={color_s * 100:6.2f}%"
        )

    print("-" * 80)
    if accepted:
        print(f"Decision: ACCEPT -> {top1[0].name} ({top1[1] * 100:.2f}%), gap={gap * 100:.2f}%")
    else:
        print(
            "Decision: UNCERTAIN -> keep Top candidates for manual review "
            f"(top1={top1[1] * 100:.2f}%, gap={gap * 100:.2f}%)"
        )


if __name__ == "__main__":
    main()
