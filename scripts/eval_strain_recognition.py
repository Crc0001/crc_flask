"""菌种识别评测脚本

用与生产 orb_detect 相同的管线（培养皿裁剪 -> 切片选块聚合 -> 整皿覆盖）
对两个数据集逐一评测：
  - test_split : 划分前的原始（已裁剪皿图，1600x1200，44 个菌种）
  - yolo_dataset: 原始带皿图（3072x4096，33 个菌种，其中仅 3 个在分类器 44 类内）

每个菌种随机抽样 10 张（seed 固定），统计 Top1/Top3 命中率。
结果输出到 test_results/。
"""

import csv
import json
import os
import random
import sys
import time

import cv2
import numpy as np

# 脚本位于 scripts/：把仓库根目录加入 sys.path，保证可 import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.crop_plate_batch import crop_plate
from app.services.recognition import (
    ENABLE_PLATE_CROP,
    _select_detection_image,
    _should_slice_image,
    _training_view,
)
from app.services.yolo_service import classify_images

TEST_SPLIT_ROOT = r"C:\Users\Administrator\Desktop\ai_des\test_split"
YOLO_ROOT = r"C:\Users\Administrator\Desktop\ai_des\yolo_dataset"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results")
SAMPLE_PER_STRAIN = 10
SEED = 42

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# yolo_dataset 文件夹 -> 分类器类别名（仅在 44 类内的菌种）
IN_CLASS_MAP = {
    "孔氏葡萄球菌Staphylococcus cohnii": "Staphylococcus cohnii",
    "短小芽孢杆菌 Bacillus pumilus": "Bacillus pumilus",
    "蜡样芽孢杆菌复合群 Bacillus cereus group": "Bacillus cereus",
}


def norm_name(value):
    return " ".join(str(value or "").split()).casefold()


def list_image_files(folder):
    files = []
    for dirpath, _, filenames in os.walk(folder):
        for name in filenames:
            if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                files.append(os.path.join(dirpath, name))
    return sorted(files)


def read_bgr(path):
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return image


def process_image(image_bgr):
    """复刻生产 orb_detect 的图像处理与识别链路，返回识别结果与耗时。"""
    start = time.time()
    detection_image = image_bgr
    plate_geometry = None
    plate_crop = {"detected": False, "applied": False, "confidence": None}
    is_large = _should_slice_image(image_bgr.shape[1], image_bgr.shape[0])

    if ENABLE_PLATE_CROP and is_large:
        try:
            cropped, det = crop_plate(image_bgr)
            apply_crop = (
                det.confidence >= 0.80
                and "little_background_removed" not in det.review_reasons
            )
            if apply_crop:
                detection_image = cropped
            origin_x = det.x1 if apply_crop else 0
            origin_y = det.y1 if apply_crop else 0
            plate_geometry = {
                "cx": det.cx - origin_x,
                "cy": det.cy - origin_y,
                "radius": det.radius,
            }
            plate_crop = {
                "detected": True,
                "applied": apply_crop,
                "confidence": round(float(det.confidence), 6),
            }
        except Exception as exc:
            plate_crop["error"] = str(exc)

    # 与生产 orb_detect 一致：切片前先保存整皿图（切片后 detection_image 会被重绑定为最佳块）
    whole_plate_image = detection_image
    detection_image, _, selected_classification, image_selection = (
        _select_detection_image(
            detection_image,
            None,
            plate_geometry=plate_geometry,
            force_slice=is_large,
        )
    )
    classification = selected_classification
    if classification is None:
        results = classify_images([detection_image])
        classification = results[0] if results else None

    # 整皿覆盖逻辑（与生产 orb_detect 一致：训练域视图 中心75%方窗->短边1200）
    whole_plate_classification = None
    if is_large:
        try:
            plate_view = _training_view(whole_plate_image)
            wp_results = classify_images([plate_view])
            whole_plate_classification = wp_results[0] if wp_results else None
        except Exception:
            whole_plate_classification = None
    if whole_plate_classification and whole_plate_classification.get("top3"):
        wp_conf = whole_plate_classification["top3"][0]["confidence"]
        wp_risk = (whole_plate_classification.get("input_risk") or {}).get("level")
        tile_risk = (classification or {}).get("input_risk") or {}
        tile_conf = (
            (classification or {}).get("top3") or [{"confidence": 0.0}]
        )[0]["confidence"]
        if wp_conf >= 0.15 or wp_conf >= tile_conf or tile_conf < 0.4:
            classification = whole_plate_classification
            if wp_risk == "high" and tile_risk.get("level") != "high":
                classification = dict(classification)
                risk = dict(classification.get("input_risk") or {})
                risk.update({"level": "medium", "label": "需复核"})
                classification["input_risk"] = risk

    elapsed = time.time() - start
    return classification, plate_crop, image_selection, elapsed


def evaluate_dataset(dataset_name, root, strain_dirs, ground_truth_fn):
    details = []
    summary = []
    rng = random.Random(SEED)
    for strain_index, strain_dir in enumerate(strain_dirs, start=1):
        strain_path = os.path.join(root, strain_dir)
        files = list_image_files(strain_path)
        if not files:
            print(f"[{dataset_name}] {strain_dir}: 无图片，跳过", flush=True)
            continue
        sample = rng.sample(files, min(SAMPLE_PER_STRAIN, len(files)))
        true_name, in_class = ground_truth_fn(strain_dir)
        hit1 = 0
        hit3 = 0
        confs = []
        for image_index, file_path in enumerate(sample, start=1):
            try:
                image = read_bgr(file_path)
                if image is None:
                    raise ValueError("imdecode 失败")
                classification, plate_crop, image_selection, elapsed = process_image(image)
            except Exception as exc:
                classification = None
                plate_crop = {"error": str(exc)}
                image_selection = {}
                elapsed = 0.0
            pred_top1 = ""
            pred_top3 = []
            confidence = 0.0
            risk_level = ""
            if classification and classification.get("top3"):
                pred_top1 = classification["top3"][0].get("species_name", "")
                pred_top3 = [
                    {
                        "species_name": item.get("species_name", ""),
                        "confidence": item.get("confidence", 0.0),
                    }
                    for item in classification["top3"]
                ]
                confidence = pred_top3[0]["confidence"]
                risk_level = (classification.get("input_risk") or {}).get("level", "")
            correct1 = bool(pred_top1) and norm_name(pred_top1) == norm_name(true_name)
            correct3 = any(
                norm_name(item["species_name"]) == norm_name(true_name)
                for item in pred_top3
            )
            hit1 += int(correct1)
            hit3 += int(correct3)
            confs.append(confidence)
            details.append({
                "dataset": dataset_name,
                "strain": strain_dir,
                "ground_truth": true_name,
                "in_class": in_class,
                "file": file_path,
                "pred_top1": pred_top1,
                "pred_top3": [item["species_name"] for item in pred_top3],
                "top1_confidence": confidence,
                "risk_level": risk_level,
                "correct_top1": correct1,
                "correct_top3": correct3,
                "plate_detected": plate_crop.get("detected", False),
                "plate_applied": plate_crop.get("applied", False),
                "plate_confidence": plate_crop.get("confidence"),
                "slice_applied": image_selection.get("applied", False),
                "aggregated": image_selection.get("aggregated", False),
                "aggregated_tiles": image_selection.get("aggregated_tiles", 0),
                "elapsed_sec": round(elapsed, 3),
                "error": plate_crop.get("error"),
            })
            print(
                f"[{dataset_name}] {strain_index}/{len(strain_dirs)} "
                f"{strain_dir} 图{image_index}/{len(sample)} "
                f"pred={pred_top1 or 'ERROR'} hit1={correct1} conf={confidence:.3f} "
                f"crop={plate_crop.get('applied', False)} agg={image_selection.get('aggregated', False)}/{image_selection.get('aggregated_tiles', 0)}",
                flush=True,
            )
        n = len(sample)
        summary.append({
            "dataset": dataset_name,
            "strain": strain_dir,
            "ground_truth": true_name,
            "in_class": in_class,
            "n": n,
            "top1_correct": hit1,
            "top3_correct": hit3,
            "top1_acc": round(hit1 / n, 4) if n else None,
            "top3_acc": round(hit3 / n, 4) if n else None,
            "avg_confidence": round(float(np.mean(confs)), 4) if confs else None,
        })
    return details, summary


def test_split_truth(strain_dir):
    return strain_dir, True


def yolo_truth(strain_dir):
    mapped = IN_CLASS_MAP.get(strain_dir)
    if mapped:
        return mapped, True
    return strain_dir, False


def collect_strain_dirs(root):
    dirs = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            dirs.append(name)
    return dirs


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_details = []
    all_summary = []

    test_split_dirs = []
    for group in collect_strain_dirs(TEST_SPLIT_ROOT):
        group_path = os.path.join(TEST_SPLIT_ROOT, group)
        for name in sorted(os.listdir(group_path)):
            if os.path.isdir(os.path.join(group_path, name)):
                test_split_dirs.append((group, name))
    print(f"test_split 菌种分组: {len(test_split_dirs)}", flush=True)
    for group, name in test_split_dirs:
        details, summary = evaluate_dataset(
            "test_split",
            os.path.join(TEST_SPLIT_ROOT, group),
            [name],
            test_split_truth,
        )
        all_details.extend(details)
        all_summary.extend(summary)

    yolo_dirs = collect_strain_dirs(YOLO_ROOT)
    print(f"yolo_dataset 菌种: {len(yolo_dirs)}", flush=True)
    details, summary = evaluate_dataset(
        "yolo_dataset", YOLO_ROOT, yolo_dirs, yolo_truth
    )
    all_details.extend(details)
    all_summary.extend(summary)

    detail_path = os.path.join(OUT_DIR, "eval_details.json")
    summary_path = os.path.join(OUT_DIR, "eval_summary.csv")
    with open(detail_path, "w", encoding="utf-8") as fh:
        json.dump(all_details, fh, ensure_ascii=False, indent=2)
    with open(summary_path, "w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = [
            "dataset", "strain", "ground_truth", "in_class", "n",
            "top1_correct", "top3_correct", "top1_acc", "top3_acc",
            "avg_confidence",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_summary)

    # 汇总
    for dataset in ("test_split", "yolo_dataset"):
        rows = [r for r in all_summary if r["dataset"] == dataset]
        in_rows = [r for r in rows if r["in_class"]]
        for label, subset in (("全部菌种", rows), ("分类器44类内菌种", in_rows)):
            if not subset:
                continue
            n_total = sum(r["n"] for r in subset)
            h1 = sum(r["top1_correct"] for r in subset)
            h3 = sum(r["top3_correct"] for r in subset)
            print(
                f"[汇总] {dataset} {label}: 菌种数={len(subset)} 图数={n_total} "
                f"Top1={h1}/{n_total}={h1 / n_total:.2%} "
                f"Top3={h3}/{n_total}={h3 / n_total:.2%}",
                flush=True,
            )
    print(f"结果文件: {detail_path}", flush=True)
    print(f"结果文件: {summary_path}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
