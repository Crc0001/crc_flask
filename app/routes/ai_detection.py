import os
import json
import uuid
from io import BytesIO
from datetime import datetime
from flask import Blueprint, render_template, request, current_app, url_for, jsonify
from werkzeug.utils import secure_filename
import cv2
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models.sample_lite import SampleLite
from app.models.sample import Sample
from app.models import BacdiveRecord, BacdiveStrainMatch, Strain
from app.extensions import db
from app.services.yolo_service import (
    HWISHAI_CLASSIFIER_MODEL,
    classify_images,
    fuse_predictions,
)
from crop_plate_batch import crop_plate
import pandas as pd
from flask import send_file

ai_detection_bp = Blueprint("ai_detection", __name__)

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
MALDI_UPLOAD_DIR = "static/maldi_uploads"
ENABLE_PLATE_CROP = True  # 仅对大图启用，并要求培养皿检测达到可信阈值
SLICE_TRIGGER_SHORT_SIDE = 1200
SLICE_TRIGGER_LONG_SIDE = 1600
SLICE_SIZE = 448
SLICE_CANDIDATE_COUNT = 8  # 两阶段选块：仅对内容分最高的少量切片分类，再做概率加权聚合
SLICE_MIN_STD = 8.0
SLICE_MIN_EDGE_RATIO = 0.001
SLICE_MIN_PLATE_COVERAGE = 0.985
# 选块优先档：菌落数 <= 该值的切片计满分并优先作为展示块（菌少、可读性好）。
# 改这里即可调整"优先取多少菌以内的图"；全皿没有此类块时自动退回最优块。
SLICE_PREFERRED_MAX_COLONIES = 15
TRAINING_VIEW_SIZE = 1200  # 分类器训练图短边；把原始皿还原到该尺度再分类，命中率大幅提升


def _strain_match_candidates():
    strains = Strain.query.filter(Strain.is_active.is_(True)).all()
    knowledge_records = dict(
        db.session.query(
            BacdiveStrainMatch.strain_id,
            db.func.min(BacdiveStrainMatch.bacdive_record_id),
        )
        .group_by(BacdiveStrainMatch.strain_id)
        .all()
    )
    return [
        {
            "strain_id": strain.id,
            "knowledge_record_id": knowledge_records.get(strain.id),
            "strain_name": strain.name or strain.scientific_name or f"菌种#{strain.id}",
            "scientific_name": strain.scientific_name or "",
            "alias": strain.alias or "",
            "category": strain.category or "",
        }
        for strain in strains
    ]


def _read_image_bgr(image_bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img



def _center_crop(img_bgr, crop_ratio=0.8):
    crop_ratio = float(np.clip(crop_ratio, 0.3, 1.0))
    if crop_ratio >= 0.999:
        return img_bgr

    h, w = img_bgr.shape[:2]
    ch, cw = int(h * crop_ratio), int(w * crop_ratio)
    y1 = (h - ch) // 2
    x1 = (w - cw) // 2
    return img_bgr[y1:y1 + ch, x1:x1 + cw]


def _resize_short(img_bgr, size):
    """短边缩放到指定尺寸，保持宽高比。"""
    h, w = img_bgr.shape[:2]
    scale = float(size) / float(min(h, w))
    return cv2.resize(
        img_bgr,
        (int(round(w * scale)), int(round(h * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _training_view(img_bgr):
    """还原分类器训练域视图：中心 75% 方窗 + 短边缩放到训练尺寸。

    训练图是 1600x1200 裁剪皿；BioCLIP 压到 224 后模型实际看到的是
    中心 1200x1200 窗口。原始皿直接分类时菌落尺度与训练域偏差 2~3 倍，
    是原始皿识别率低的主因。实测（uploads 132 张）：6% -> 33% Top1。
    """
    h, w = img_bgr.shape[:2]
    q = int(min(h, w) * 0.75)
    x1 = (w - q) // 2
    y1 = (h - q) // 2
    return _resize_short(img_bgr[y1:y1 + q, x1:x1 + q], TRAINING_VIEW_SIZE)


def _tile_positions(length, tile_size, stride):
    if length <= tile_size:
        return [0]
    positions = list(range(0, length - tile_size + 1, stride))
    last_position = length - tile_size
    if positions[-1] != last_position:
        positions.append(last_position)
    return positions


def _should_slice_image(width, height):
    short_side, long_side = sorted((int(width), int(height)))
    return (
        short_side > SLICE_TRIGGER_SHORT_SIDE
        and long_side > SLICE_TRIGGER_LONG_SIDE
    )


def _plate_coverage_mask(x, y, tile_size, plate_geometry):
    if not plate_geometry:
        return None, 1.0
    yy, xx = np.ogrid[y:y + tile_size, x:x + tile_size]
    radius = float(plate_geometry["radius"]) * 0.94
    mask = (
        (xx - float(plate_geometry["cx"])) ** 2
        + (yy - float(plate_geometry["cy"])) ** 2
        <= radius ** 2
    )
    return mask, float(mask.mean())


def _tile_content_score(tile, plate_mask=None):
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    gray_std = float(gray.std())
    edges = cv2.Canny(gray, 50, 150)
    edge_ratio = float((edges > 0).mean())
    if gray_std < SLICE_MIN_STD or edge_ratio < SLICE_MIN_EDGE_RATIO:
        return None

    top_hat_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (31, 31),
    )
    top_hat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, top_hat_kernel)
    bright_detail = top_hat > 10
    if plate_mask is not None:
        bright_detail &= plate_mask
    bright_detail = cv2.morphologyEx(
        bright_detail.astype(np.uint8),
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
    )

    component_count, _, stats, centroids = cv2.connectedComponentsWithStats(
        bright_detail,
        8,
    )
    colonies = []
    confluent_area = 0
    for index in range(1, component_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if area > 1200:
            confluent_area += area
        aspect_ratio = width / max(height, 1)
        fill_ratio = area / max(width * height, 1)
        if (
            8 <= area <= 1200
            and 0.45 <= aspect_ratio <= 2.20
            and fill_ratio >= 0.22
        ):
            colonies.append((area, centroids[index]))

    colony_count = len(colonies)
    if colony_count == 0:
        return None

    areas = np.asarray([item[0] for item in colonies], dtype=np.float32)
    centers = np.asarray([item[1] for item in colonies], dtype=np.float32)
    if colony_count >= 2:
        distances = np.linalg.norm(
            centers[:, None, :] - centers[None, :, :],
            axis=2,
        )
        np.fill_diagonal(distances, np.inf)
        nearest_distances = distances.min(axis=1)
        median_separation = float(np.median(nearest_distances))
        close_fraction = float((nearest_distances < 22).mean())
    else:
        median_separation = 0.0
        close_fraction = 0.0

    linearity = 1.0
    if colony_count >= 3:
        eigenvalues = np.linalg.eigvalsh(np.cov(centers.T))
        linearity = float(eigenvalues[-1] / max(eigenvalues[0], 1e-6))

    # 菌落数量：不超过优先档上限记满分（菌少优先），超过后平滑衰减
    count_score = float(
        np.exp(-max(0.0, colony_count - SLICE_PREFERRED_MAX_COLONIES) / 6.0)
    )

    # 分布均匀性：最近邻距离变异系数 + 4x4 网格菌落计数变异系数
    if colony_count >= 3 and median_separation > 0:
        nearest_cv = float(
            np.std(nearest_distances) / max(np.mean(nearest_distances), 1e-6)
        )
        nn_score = float(np.clip(1.0 - (nearest_cv - 0.35) / 0.65, 0.0, 1.0))
    else:
        nn_score = 1.0

    grid_score = 1.0
    if colony_count >= 4:
        tile_height, tile_width = gray.shape[:2]
        grid_cols = np.clip(
            (centers[:, 0] / (tile_width / 4.0)).astype(np.int32),
            0,
            3,
        )
        grid_rows = np.clip(
            (centers[:, 1] / (tile_height / 4.0)).astype(np.int32),
            0,
            3,
        )
        grid_counts = np.zeros(16, dtype=np.float32)
        np.add.at(grid_counts, grid_rows * 4 + grid_cols, 1.0)
        grid_mean = colony_count / 16.0
        grid_std = float(
            np.sqrt(max(np.mean(grid_counts ** 2) - grid_mean ** 2, 0.0))
        )
        grid_cv = grid_std / max(grid_mean, 1e-6)
        grid_score = float(np.clip(1.0 - (grid_cv - 1.0) / 1.6, 0.0, 1.0))
    uniformity_score = 0.5 * nn_score + 0.5 * grid_score

    separation_score = float(
        np.clip((median_separation - 18) / 35, 0.0, 1.0)
    )
    shape_score = 1.0 - float((areas > 300).mean())
    isolation_score = 1.0 - close_fraction
    contrast_score = min(gray_std / 25.0, 1.0)
    linearity_penalty = float(np.clip((linearity - 2) / 6, 0.0, 1.0))
    confluent_penalty = min(
        (confluent_area / float(gray.size)) / 0.10,
        1.0,
    )
    score = (
        0.30 * count_score
        + 0.20 * uniformity_score
        + 0.15 * separation_score
        + 0.15 * isolation_score
        + 0.10 * shape_score
        + 0.10 * contrast_score
        - 0.20 * linearity_penalty
        - 0.20 * confluent_penalty
    )
    return max(0.0, float(score)), colony_count

def _select_detection_image(
    image,
    image_path,
    plate_geometry=None,
    force_slice=False,
):
    height, width = image.shape[:2]
    selection = {
        "applied": False,
        "original_size": [int(width), int(height)],
        "tile_size": None,
        "total_tiles": 0,
        "sampled_tiles": 1,
        "selected_tile": None,
        "confidence": None,
    }
    if not force_slice and not _should_slice_image(width, height):
        return image, image_path, None, selection

    stride = int(SLICE_SIZE * 0.8)
    x_positions = _tile_positions(width, SLICE_SIZE, stride)
    y_positions = _tile_positions(height, SLICE_SIZE, stride)
    ranked_tiles = []
    for row, y in enumerate(y_positions):
        for column, x in enumerate(x_positions):
            tile = image[y:y + SLICE_SIZE, x:x + SLICE_SIZE]
            plate_mask, plate_coverage = _plate_coverage_mask(
                x,
                y,
                SLICE_SIZE,
                plate_geometry,
            )
            if plate_coverage < SLICE_MIN_PLATE_COVERAGE:
                continue
            scored = _tile_content_score(tile, plate_mask)
            if scored is None:
                continue
            content_score, colony_count = scored
            ranked_tiles.append({
                "image": tile,
                "content_score": content_score,
                "colony_count": colony_count,
                "plate_coverage": plate_coverage,
                "name": f"tile_r{row + 1:02d}_c{column + 1:02d}",
            })

    if not ranked_tiles:
        return image, image_path, None, selection

    ranked_tiles.sort(key=lambda item: item["content_score"], reverse=True)
    candidates = ranked_tiles[:SLICE_CANDIDATE_COUNT]
    # 训练数据是 448x448 切片（HwishAI 预处理统一压成 224x224），
    # 所以切片直接按原尺寸分类即可，无需放大，否则偏离训练分布
    classifications = classify_images([item["image"] for item in candidates])
    risk_order = {"low": 0, "medium": 1, "high": 2}

    def _pick_key(index):
        risk_level = (
            classifications[index].get("input_risk") or {}
        ).get("level", "medium")
        return (
            -float(candidates[index]["content_score"]),
            risk_order.get(risk_level, 1),
            -float(classifications[index].get("confidence", 0.0)),
        )

    # 聚合权重：内容分加权；高风险块视为无效样本，剔除出聚合
    aggregate_weights = []
    for index, item in enumerate(candidates):
        risk_level = (
            classifications[index].get("input_risk") or {}
        ).get("level", "medium")
        aggregate_weights.append(
            0.0 if risk_level == "high" else float(item["content_score"])
        )

    fused_classification = None
    fused_tile_count = 0
    if any(weight > 0 for weight in aggregate_weights):
        fused_tile_count = sum(1 for weight in aggregate_weights if weight > 0)
        fused_classification = fuse_predictions(
            classifications,
            aggregate_weights,
        )

    valid_indices = [
        index for index, weight in enumerate(aggregate_weights) if weight > 0
    ]
    if valid_indices:
        # 优先取菌落数不超过优先档上限的稀疏块（菌图可读性好、便于人工复核），
        # 稀疏块不存在时退回内容分最高的块
        sparse_indices = [
            index for index in valid_indices
            if (candidates[index].get("colony_count") or 999)
            <= SLICE_PREFERRED_MAX_COLONIES
        ]
        best_index = max(
            sparse_indices or valid_indices,
            key=lambda index: aggregate_weights[index],
        )
    else:
        # 全部高风险：退回原有选块逻辑（内容分 → 风险 → 置信度）
        best_index = min(range(len(classifications)), key=_pick_key)
    best_tile = candidates[best_index]
    best_classification = (
        fused_classification
        if fused_classification is not None
        else classifications[best_index]
    )
    selection_score = (
        0.75 * best_tile["content_score"]
        + 0.25 * float(best_classification.get("confidence", 0.0))
    )
    selection.update({
        "applied": True,
        "tile_size": [SLICE_SIZE, SLICE_SIZE],
        "total_tiles": len(x_positions) * len(y_positions),
        "eligible_tiles": len(ranked_tiles),
        "sampled_tiles": len(candidates),
        "selected_tile": best_tile["name"],
        "selected_colony_count": best_tile.get("colony_count"),
        "candidate_colony_counts": [
            item.get("colony_count") for item in candidates
        ],
        "content_score": round(best_tile["content_score"], 6),
        "plate_coverage": round(best_tile["plate_coverage"], 6),
        "selection_score": round(selection_score, 6),
        "confidence": round(float(best_classification.get("confidence", 0.0)), 6),
        "aggregated": fused_classification is not None,
        "aggregated_tiles": fused_tile_count,
    })
    return best_tile["image"], image_path, best_classification, selection

def _preprocess_for_match(img_bgr, size=256, crop_ratio=0.8):
    cropped = _center_crop(img_bgr, crop_ratio=crop_ratio)
    return cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)


def _normalize_gray_for_features(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _ratio_good_matches(des1, des2, norm_type, ratio=0.75):
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


def _orb_similarity(q_img, db_img):
    gray_q = _normalize_gray_for_features(q_img)
    gray_d = _normalize_gray_for_features(db_img)

    orb = cv2.ORB_create(nfeatures=1500)
    kp1, des1 = orb.detectAndCompute(gray_q, None)
    kp2, des2 = orb.detectAndCompute(gray_d, None)

    if des1 is not None and des2 is not None and len(kp1) >= 10 and len(kp2) >= 10:
        good = _ratio_good_matches(des1, des2, cv2.NORM_HAMMING, ratio=0.75)
        denom = max(min(len(kp1), len(kp2)), 1)
        return float(np.clip(good / float(denom), 0.0, 1.0))

    akaze = cv2.AKAZE_create()
    kp1, des1 = akaze.detectAndCompute(gray_q, None)
    kp2, des2 = akaze.detectAndCompute(gray_d, None)
    if des1 is None or des2 is None or len(kp1) == 0 or len(kp2) == 0:
        return 0.0

    good = _ratio_good_matches(des1, des2, cv2.NORM_HAMMING, ratio=0.78)
    denom = max(min(len(kp1), len(kp2)), 1)
    return float(np.clip(good / float(denom), 0.0, 1.0))


def _color_hist_similarity(q_img, db_img):
    hsv_q = cv2.cvtColor(q_img, cv2.COLOR_BGR2HSV)
    hsv_d = cv2.cvtColor(db_img, cv2.COLOR_BGR2HSV)

    hist_size = [32, 32]
    ranges = [0, 180, 0, 256]
    channels = [0, 1]

    hq = cv2.calcHist([hsv_q], channels, None, hist_size, ranges)
    hd = cv2.calcHist([hsv_d], channels, None, hist_size, ranges)
    cv2.normalize(hq, hq, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(hd, hd, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    corr = cv2.compareHist(hq, hd, cv2.HISTCMP_CORREL)
    return float(np.clip((corr + 1.0) / 2.0, 0.0, 1.0))


@ai_detection_bp.route("/api/orb_detect", methods=["POST"])
def orb_detect():
    try:
        file = request.files.get("image")
        if not file or file.filename == "":
            return jsonify({"success": False, "message": "请上传图片文件"})

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'jfif', 'heic', 'heif'}

        mime_type = (file.mimetype or '').lower()
        is_image_mime = mime_type.startswith('image/')
        is_allowed_ext = ext in allowed_extensions

        if not is_image_mime and not is_allowed_ext:
            return jsonify({
                "success": False,
                "message": "不支持的文件格式，请上传图片文件（png/jpg/jpeg/gif/bmp/tiff/webp/jfif/heic/heif）"
            })

        image_bytes = file.read()
        if not image_bytes:
            return jsonify({"success": False, "message": "图片内容为空"})

        upload_dir = os.path.join(current_app.root_path, UPLOAD_DIR)
        result_dir = os.path.join(current_app.root_path, RESULT_DIR)
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)

        stem, original_ext = os.path.splitext(filename)
        filename = f"{stem or 'upload'}_{uuid.uuid4().hex[:12]}{original_ext or '.jpg'}"
        image_path = os.path.join(upload_dir, filename)
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        q_raw = _read_image_bgr(image_bytes)
        if q_raw is None:
            return jsonify({"success": False, "message": "图片读取失败，请更换图片重试"})

        plate_crop = {
            "detected": False,
            "applied": False,
            "confidence": None,
            "method": None,
            "needs_review": False,
            "review_reasons": [],
        }
        detection_image = q_raw
        plate_geometry = None
        is_large_image = _should_slice_image(q_raw.shape[1], q_raw.shape[0])
        if ENABLE_PLATE_CROP and is_large_image:
            try:
                cropped_image, crop_detection = crop_plate(q_raw)
                crop_confidence = float(crop_detection.confidence)
                crop_reasons = list(crop_detection.review_reasons)
                apply_crop = (
                    crop_confidence >= 0.80
                    and "little_background_removed" not in crop_reasons
                )
                if apply_crop:
                    detection_image = cropped_image
                # 即使未裁剪，也用检测到的培养皿几何过滤切片，避免背景块参与选块
                origin_x = crop_detection.x1 if apply_crop else 0
                origin_y = crop_detection.y1 if apply_crop else 0
                plate_geometry = {
                    "cx": crop_detection.cx - origin_x,
                    "cy": crop_detection.cy - origin_y,
                    "radius": crop_detection.radius,
                }
                plate_crop.update({
                    "detected": True,
                    "applied": apply_crop,
                    "confidence": round(crop_confidence, 6),
                    "method": crop_detection.method,
                    "needs_review": crop_detection.needs_review,
                    "review_reasons": crop_reasons,
                    "bbox": [
                        crop_detection.x1,
                        crop_detection.y1,
                        crop_detection.x2,
                        crop_detection.y2,
                    ],
                    "output_size": [
                        int(detection_image.shape[1]),
                        int(detection_image.shape[0]),
                    ],
                })
            except (ValueError, cv2.error) as exc:
                plate_crop["reason"] = str(exc)

        whole_plate_image = detection_image
        detection_image, _, selected_classification, image_selection = (
            _select_detection_image(
                detection_image,
                image_path,
                plate_geometry=plate_geometry,
                force_slice=is_large_image,
            )
        )
        classification = selected_classification
        if classification is None:
            classifications = classify_images([detection_image])
            classification = classifications[0] if classifications else None
        if not classification or not classification.get("top3"):
            return jsonify({
                "success": False,
                "message": "HwishAI未返回菌种候选",
            })

        # 整皿图分类：还原训练域视图（中心75%方窗 -> 短边1200），
        # 实测原始皿 Top1 6% -> 33%，远超原生分辨率整皿与 448 切片路径
        whole_plate_classification = None
        if is_large_image:
            try:
                plate_view = _training_view(whole_plate_image)
                wp_results = classify_images([plate_view])
                whole_plate_classification = wp_results[0] if wp_results else None
            except Exception:
                whole_plate_classification = None

        low_confidence = False
        if whole_plate_classification and whole_plate_classification.get("top3"):
            wp_conf = whole_plate_classification["top3"][0]["confidence"]
            wp_risk = (whole_plate_classification.get("input_risk") or {}).get("level")
            tile_risk = (classification.get("input_risk") or {}).get("level")
            tile_conf = classification["top3"][0]["confidence"]
            # 整皿训练域视图是单路径中最准的（实测 33% > 切片 12%），
            # 只要它置信度不算太低就优先采用；仅在其极弱时回退到置信度更高的路径
            if wp_conf >= 0.15 or wp_conf >= tile_conf or tile_conf < 0.4:
                classification = whole_plate_classification
                # ---- 门禁已注释（演示模式）：不再对整皿视角做风险降级 ----
                # if wp_risk == "high" and tile_risk != "high":
                #     risk = classification.get("input_risk") or {}
                #     risk["level"] = "medium"
                #     risk["label"] = "需复核"
                #     risk["message"] = (
                #         "整皿图置信度有限，Top3可作为候选，"
                #         "建议结合MALDI-TOF、16S或其他检测结果复核。"
                #     )
                #     classification["input_risk"] = risk
        if classification["top3"][0]["confidence"] < 0.4:
            low_confidence = True

        result_filename = (
            f"{os.path.splitext(filename)[0]}_classified.jpg"
        )
        result_path = os.path.join(result_dir, result_filename)
        if not cv2.imwrite(result_path, detection_image):
            raise ValueError("识别结果图片保存失败")

        raw_image_confidence = float(classification.get("confidence", 0.0))
        # ---- 门禁已注释（演示模式）：缺失 input_risk 时也给无害默认值 ----
        input_risk = classification.get("input_risk") or {
            "level": "low",
            "label": "未启用",
            "score": 0.0,
            "soft_only": True,
            "temporary_gate": False,
            "message": "门禁已关闭（演示模式），Top3 直接来自封闭分类器与 XGBoost 打分。",
            "reasons": [],
            "signals": {},
        }
        image_selection["confidence"] = round(raw_image_confidence, 6)
        image_selection["risk_level"] = input_risk.get("level", "medium")

        # ---- 门禁已注释（演示模式）：高风险拒答不再生效，任何图都正常返回 Top3 ----
        # if input_risk.get("level") == "high":
        #     rejection_message = (
        #         "图片未通过输入有效性检查，请上传直接拍摄的培养皿或菌落原图"
        #     )
        #     return jsonify({
        #         "success": True,
        #         "accepted": False,
        #         "code": "input_risk_rejected",
        #         "message": rejection_message,
        #         "candidates": [],
        #         "detections": [],
        #         "result_path": result_path,
        #         "result_image_url": url_for(
        #             "static",
        #             filename=f"results/{result_filename}",
        #         ),
        #         "recommended_strain_name": "",
        #         "recommended_match_score": 0.0,
        #         "input_risk": input_risk,
        #         "analysis_text": f"{rejection_message}。{input_risk.get('message', '')}",
        #         "plate_crop": plate_crop,
        #         "image_selection": image_selection,
        #     })

        strain_candidates = _strain_match_candidates()
        strain_by_scientific_name = {
            " ".join(candidate.get("scientific_name", "").split()).casefold(): candidate
            for candidate in strain_candidates
            if candidate.get("scientific_name")
        }
        classifier_aliases = {
            "Faucicola osloensis": "Moraxella osloensis",
            "Staphylococcus ureilyticu": "Staphylococcus ureilyticus",
        }
        knowledge_lookup_names = [
            classifier_aliases.get(item.get("species_name", ""), item.get("species_name", ""))
            for item in classification["top3"]
            if item.get("species_name")
        ]
        knowledge_by_scientific_name = {}
        if knowledge_lookup_names:
            knowledge_records = (
                db.session.query(BacdiveRecord.id, BacdiveRecord.species_name)
                .filter(BacdiveRecord.species_name.in_(knowledge_lookup_names))
                .order_by(BacdiveRecord.bacdive_id)
                .all()
            )
            for record_id, species_name in knowledge_records:
                normalized_name = " ".join((species_name or "").split()).casefold()
                knowledge_by_scientific_name.setdefault(normalized_name, record_id)

        top_candidates = []
        for rank, item in enumerate(classification["top3"], start=1):
            scientific_name = item.get("species_name", "")
            lookup_name = classifier_aliases.get(scientific_name, scientific_name)
            normalized_lookup_name = " ".join(lookup_name.split()).casefold()
            strain = strain_by_scientific_name.get(normalized_lookup_name)
            knowledge_record_id = (
                strain.get("knowledge_record_id") if strain else None
            ) or knowledge_by_scientific_name.get(normalized_lookup_name)
            classifier_confidence = float(item.get("confidence", 0.0))
            classifier_chinese_name = item.get("chinese_name", "")
            top_candidates.append({
                "rank": rank,
                "matched_strain_id": strain.get("strain_id") if strain else None,
                "matched_strain_name": (
                    strain.get("strain_name")
                    if strain
                    else classifier_chinese_name or scientific_name
                ),
                "classifier_species_name": scientific_name,
                "classifier_chinese_name": classifier_chinese_name,
                "classifier_confidence": classifier_confidence,
                "effective_confidence": classifier_confidence,
                "match_score": classifier_confidence,
                "image_score": classifier_confidence,
                "low_confidence": classifier_confidence < 0.5,
                "input_risk_level": input_risk.get("level", "medium"),
                "recognition_model": f"HwishAI {HWISHAI_CLASSIFIER_MODEL}",
                "knowledge_url": (
                    url_for(
                        "strain_showcase.detail",
                        record_id=knowledge_record_id,
                    )
                    if knowledge_record_id
                    else None
                ),
            })

        top_detection = top_candidates[0]
        selection_summary = (
            f"大图已优先选取培养皿内部的孤立单菌落切片，"
            if image_selection["applied"]
            else ""
        )
        risk_summary = input_risk.get(
            "message",
            "软风险信号暂不可用，Top3仅作为候选结果。",
        )
        analysis_text = (
            f"{selection_summary}"
            f"HwishAI已完成菌种识别。"
            f"当前最佳菌种：{top_detection.get('matched_strain_name', '未知菌种')}"
            f"（相对匹配度{top_detection.get('match_score', 0.0) * 100:.2f}%）。"
            f"{risk_summary}"
        )
        if low_confidence:
            analysis_text += "当前识别置信度较低，建议结合原始平板形态或其他检测结果复核。"

        return jsonify({
            "success": True,
            "accepted": True,
            "message": "HwishAI菌种识别完成（BioCLIP + XGBoost）",
            "candidates": top_candidates,
            "detections": [],
            "result_path": result_path,
            "result_image_url": url_for(
                "static",
                filename=f"results/{result_filename}",
            ),
            "recommended_strain_name": top_detection.get("matched_strain_name", ""),
            "recommended_match_score": top_detection.get("match_score", 0.0),
            "input_risk": input_risk,
            "analysis_text": analysis_text,
            "plate_crop": plate_crop,
            "image_selection": image_selection,
            "low_confidence": low_confidence,
        })
    except Exception as e:
        print(f"菌落检测识别失败: {str(e)}")
        return jsonify({"success": False, "message": f"菌落检测识别失败: {str(e)}"})


@ai_detection_bp.route("/ai_detection", methods=["GET"])
def ai_detection():
    # GET仅渲染页面，检测由上传接口按需执行
    location_hierarchy = SampleLite.get_hierarchical_data()
    return render_template(
        "ai_detection.html",
        image_url=None,
        results=[],
        final_result=None,
        message=None,
        error_message=None,
        detect_count=0,
        maldi_image_url=None,
        location_hierarchy=json.dumps(location_hierarchy)
    )


@ai_detection_bp.route("/api/save_detection_report", methods=["POST"])
def save_detection_report():
    """保存检测报告到菌种数据库（sample表）"""
    try:
        sample_code = (request.form.get("sample_code") or "").strip()
        collect_date_str = (request.form.get("collect_date") or "").strip()
        source_location = (request.form.get("source_location") or "").strip()
        strain_name = (request.form.get("strain_name") or "").strip()

        if not sample_code:
            return jsonify({
                "success": False,
                "message": "缺少样品编号，请在报告中填写后再录入"
            })

        if not strain_name:
            return jsonify({
                "success": False,
                "message": "缺少菌种名称，请先完成菌落识别或手动填写"
            })

        collect_date = None
        if collect_date_str:
            try:
                collect_date = datetime.strptime(collect_date_str, "%Y-%m-%d")
            except ValueError:
                return jsonify({
                    "success": False,
                    "message": "采集日期格式错误，应为 YYYY-MM-DD"
                })

        maldi_file = request.files.get("maldi_image")
        mass_spectrum = maldi_file.read() if maldi_file and maldi_file.filename else None

        target = Sample.query.filter_by(sample_code=sample_code).first()
        now = datetime.now()

        if target:
            target.collect_date = collect_date
            target.collect_location = source_location or target.collect_location
            target.final_strain_name = strain_name
            target.last_detect_time = now
            target.last_detect_count = 1
            if mass_spectrum:
                target.mass_spectrum = mass_spectrum
            action = "updated"
        else:
            target = Sample(
                sample_code=sample_code,
                collect_date=collect_date,
                collect_location=source_location or None,
                final_strain_name=strain_name,
                last_detect_time=now,
                last_detect_count=1,
                mass_spectrum=mass_spectrum
            )
            db.session.add(target)
            action = "created"

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "报告已录入菌种数据库(sample)",
            "sample_id": target.id,
            "action": action,
            "list_url": url_for("strain_db.index")
        })

    except Exception as e:
        db.session.rollback()
        print(f"保存检测报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"保存失败: {str(e)}"
        })


@ai_detection_bp.route("/api/check_sample_code", methods=["GET"])
def check_sample_code():
    """检查样品编号是否已存在于菌种数据库，存在则返回现有记录信息"""
    try:
        code = (request.args.get("sample_code") or "").strip()
        if not code:
            return jsonify({"success": True, "exists": False})

        target = Sample.query.filter_by(sample_code=code).first()
        if not target:
            return jsonify({"success": True, "exists": False})

        return jsonify({
            "success": True,
            "exists": True,
            "existing": {
                "sample_id": target.id,
                "strain_name": target.final_strain_name or "",
                "collect_date": target.collect_date.strftime("%Y-%m-%d") if target.collect_date else "",
                "location": target.collect_location or "",
                "last_detect_time": target.last_detect_time.strftime("%Y-%m-%d %H:%M") if target.last_detect_time else "",
            },
        })
    except Exception as e:
        print(f"检查样品编号失败: {str(e)}")
        return jsonify({"success": False, "message": f"检查失败: {str(e)}"})


def _get_pdf_chinese_font_name():
    candidates = [
        ("PDF_CN", r"C:\\Windows\\Fonts\\msyh.ttc"),
        ("PDF_CN", r"C:\\Windows\\Fonts\\simsun.ttc"),
        ("PDF_CN", r"C:\\Windows\\Fonts\\simhei.ttf"),
        ("PDF_CN", r"C:\\Windows\\Fonts\\simfang.ttf"),
    ]

    for font_name, font_path in candidates:
        if not os.path.exists(font_path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
        except Exception:
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path, subfontIndex=0))
                return font_name
            except Exception:
                continue

    return None


def _draw_wrapped_text(pdf, text, x, y, max_width, font_name, font_size, line_height=18):
    content = text or ''
    if not content:
        return y - line_height

    pdf.setFont(font_name, font_size)
    line = ''
    for ch in content:
        candidate = line + ch
        if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
            line = candidate
        else:
            if line:
                pdf.drawString(x, y, line)
                y -= line_height
            line = ch

    if line:
        pdf.drawString(x, y, line)
        y -= line_height

    return y


def _draw_image(pdf, image_bytes, title, x, y, font_name, width=240, height=160):
    pdf.setFont(font_name, 11)
    pdf.drawString(x, y, title)
    y -= 12

    if not image_bytes:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y - 18, '未上传')
        return y - height

    try:
        image = ImageReader(BytesIO(image_bytes))
        pdf.drawImage(image, x, y - height, width=width, height=height, preserveAspectRatio=True, anchor='c')
    except Exception:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y - 18, '图片读取失败')

    return y - height


@ai_detection_bp.route('/api/export_detection_report_pdf', methods=['POST'])
def export_detection_report_pdf():
    try:
        sample_code = (request.form.get('sample_code') or '').strip()
        collect_date = (request.form.get('collect_date') or '').strip()
        source_location = (request.form.get('source_location') or '').strip()
        strain_name = (request.form.get('strain_name') or '').strip()
        detection_result = (request.form.get('detection_result') or '').strip()
        maldi_candidates_raw = (request.form.get('maldi_candidates') or '').strip()
        sequence_16s = (request.form.get('sequence_16s') or '').strip()
        result_16s_raw = (request.form.get('result_16s') or '').strip()
        image_file = request.files.get('image')
        if not image_file or not image_file.filename:
            return jsonify({'success': False, 'message': '请先上传样本图片'}), 400

        sample_image_bytes = image_file.read()
        maldi_file = request.files.get('maldi_image')
        maldi_image_bytes = maldi_file.read() if maldi_file and maldi_file.filename else None

        try:
            maldi_candidates = json.loads(maldi_candidates_raw) if maldi_candidates_raw else []
        except (TypeError, ValueError):
            maldi_candidates = []
        if not isinstance(maldi_candidates, list):
            maldi_candidates = []

        try:
            result_16s = json.loads(result_16s_raw) if result_16s_raw else None
        except (TypeError, ValueError):
            result_16s = None
        if not isinstance(result_16s, dict):
            result_16s = None

        font_name = _get_pdf_chinese_font_name()
        if not font_name:
            return jsonify({'success': False, 'message': '未找到可用中文字体，请检查服务器字体配置'}), 500

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        page_width, page_height = A4

        y = page_height - 50
        pdf.setFont(font_name, 16)
        pdf.drawString(40, y, '菌种检测报告')
        y -= 28

        pdf.setFont(font_name, 11)
        y = _draw_wrapped_text(pdf, f'样品编号：{sample_code or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y = _draw_wrapped_text(pdf, f'采集日期：{collect_date or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y = _draw_wrapped_text(pdf, f'来源位置：{source_location or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y = _draw_wrapped_text(pdf, f'菌种名称：{strain_name or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y -= 8

        pdf.setFont(font_name, 11)
        pdf.drawString(40, y, '检测结论：')
        y -= 18

        conclusion_text = (detection_result or strain_name or '未填写').splitlines() or ['未填写']
        for line in conclusion_text:
            y = _draw_wrapped_text(pdf, line, 40, y, page_width - 80, font_name, 10, line_height=15)
            if y < 260:
                pdf.showPage()
                y = page_height - 50
                pdf.setFont(font_name, 10)

        if y < 260:
            pdf.showPage()
            y = page_height - 50

        left_x = 40
        right_x = page_width / 2 + 10
        image_top_y = y
        _draw_image(pdf, sample_image_bytes, '样本图片', left_x, image_top_y, font_name)
        _draw_image(pdf, maldi_image_bytes, 'MALDI-TOF图谱', right_x, image_top_y, font_name)

        # 补充检测信息独立成页，避免长 16S 序列挤压首页图片。
        pdf.showPage()
        y = page_height - 50
        pdf.setFont(font_name, 14)
        pdf.drawString(40, y, '补充检测结果')
        y -= 28

        def ensure_detail_space(required_height=24):
            nonlocal y
            if y < 45 + required_height:
                pdf.showPage()
                y = page_height - 50

        def draw_detail_heading(title):
            nonlocal y
            ensure_detail_space(34)
            pdf.setFont(font_name, 12)
            pdf.drawString(40, y, title)
            y -= 20

        def draw_detail_text(text, font_size=10, line_height=15, x=48):
            nonlocal y
            max_width = page_width - x - 40
            source_lines = str(text or '').splitlines() or ['']
            for source_line in source_lines:
                wrapped_lines = []
                line = ''
                for ch in source_line:
                    candidate = line + ch
                    if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                        line = candidate
                    else:
                        if line:
                            wrapped_lines.append(line)
                        line = ch
                wrapped_lines.append(line)
                for wrapped_line in wrapped_lines:
                    ensure_detail_space(line_height)
                    pdf.setFont(font_name, font_size)
                    pdf.drawString(x, y, wrapped_line)
                    y -= line_height

        def report_percent(value):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return '-'
            if abs(number) <= 1:
                number *= 100
            return f'{number:.2f}%'

        draw_detail_heading('MALDI-TOF检测结果')
        if maldi_candidates:
            for index, candidate in enumerate(maldi_candidates[:5], start=1):
                if not isinstance(candidate, dict):
                    continue
                strain = candidate.get('strain_name') or '未知菌种'
                scientific = candidate.get('scientific_name') or '-'
                score = report_percent(candidate.get('score'))
                cosine = report_percent(candidate.get('cosine_sim'))
                matched_count = candidate.get('matched_count', '-')
                draw_detail_text(
                    f'{index}. {strain}（{scientific}）  综合得分：{score}；'
                    f'余弦相似度：{cosine}；匹配峰数：{matched_count}'
                )
        else:
            draw_detail_text('未进行 MALDI-TOF 检测或未获得匹配结果。')
        y -= 8

        draw_detail_heading('16S序列')
        compact_sequence = ''.join(sequence_16s.split())
        draw_detail_text(compact_sequence or '未提交 16S 序列。', font_size=9, line_height=13)
        y -= 8

        draw_detail_heading('16S RNA检测结果')
        if result_16s:
            similarity = report_percent(result_16s.get('similarity'))
            query_length = result_16s.get('query_length') or len(compact_sequence) or '-'
            draw_detail_text(f'匹配菌种：{result_16s.get("strain_name") or "未知菌种"}')
            draw_detail_text(f'拉丁名：{result_16s.get("scientific_name") or "-"}')
            draw_detail_text(f'相似度：{similarity}')
            draw_detail_text(f'最长匹配长度：{result_16s.get("match_length") or "-"} bp')
            draw_detail_text(f'查询长度：{query_length} bp')
            draw_detail_text(f'参考长度：{result_16s.get("ref_length") or "-"} bp')
        else:
            draw_detail_text('未进行 16S RNA 检测或未获得匹配结果。')

        pdf.save()
        buffer.seek(0)

        filename_code = sample_code or datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'菌种检测报告_{filename_code}.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f'导出PDF失败: {str(e)}')
        return jsonify({'success': False, 'message': f'导出PDF失败: {str(e)}'}), 500


@ai_detection_bp.route("/api/location_data", methods=["GET"])
def get_location_data():
    """API接口：获取分类数据"""
    hierarchical_data = SampleLite.get_hierarchical_data()
    return jsonify(hierarchical_data)


@ai_detection_bp.route("/ai_detection/get_excel_data", methods=["GET"])
def get_excel_data():
    """获取Excel文件数据并转换为HTML表格"""
    try:
        excel_path = os.path.join(current_app.root_path, 'static', 'maldi_results', 'analysis_result.xlsx')

        # 打印路径和存在性
        print("Excel文件路径:", excel_path)
        print("文件是否存在:", os.path.exists(excel_path))

        if not os.path.exists(excel_path):
            return jsonify({
                "success": False,
                "message": "Excel文件不存在",
                "html": """
                <div style="padding: 40px; text-align: center; color: #6c757d;">
                    <div style="font-size: 48px; margin-bottom: 20px;">❌</div>
                    <h4 style="color: #e74a3b; margin-bottom: 10px;">Excel文件未找到</h4>
                    <p>请将Excel文件放置在：static/maldi_results/analysis_result.xlsx</p>
                </div>
                """
            })

        # 读取Excel文件
        df = pd.read_excel(excel_path)

        # 转换为HTML表格（添加样式类）
        html_table = df.to_html(
            index=False,
            classes='excel-table',
            border=0,
            na_rep=''
        )

        # 美化HTML表格
        html = f"""
        <div class="excel-table-container">
            <div class="table-header">
                <h5>MALDI-TOF质谱分析结果</h5>
                <div class="table-info">
                    <span>数据来源：质谱分析系统</span>
                    <button class="btn-download" id="download-excel-btn">📥 导出Excel</button>
                </div>
            </div>
            <div class="table-wrapper">
                {html_table}
            </div>
        </div>
        """

        return jsonify({
            "success": True,
            "html": html,
            "filename": "analysis_result.xlsx",
            "download_url": url_for('static', filename='maldi_results/analysis_result.xlsx')
        })

    except Exception as e:
        print(f"读取Excel文件失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"读取Excel文件失败: {str(e)}",
            "html": f"""
            <div style="padding: 40px; text-align: center; color: #6c757d;">
                <div style="font-size: 48px; margin-bottom: 20px;">❌</div>
                <h4 style="color: #e74a3b; margin-bottom: 10px;">Excel文件读取失败</h4>
                <p>{str(e)}</p>
                <p style="margin-top: 20px;">请检查Excel文件格式是否正确</p>
            </div>
            """
        })


@ai_detection_bp.route("/download_excel", methods=["GET"])
def download_excel():
    """下载Excel文件"""
    excel_path = os.path.join(current_app.root_path, 'static', 'maldi_results', 'analysis_result.xlsx')

    if not os.path.exists(excel_path):
        return jsonify({
            "success": False,
            "message": "文件不存在"
        })

    return send_file(
        excel_path,
        as_attachment=True,
        download_name='maldi_analysis_result.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@ai_detection_bp.route("/api/upload_maldi_image", methods=["POST"])
def upload_maldi_image():
    """上传MALDI-TOF质谱图"""
    try:
        if 'maldi_image' not in request.files:
            return jsonify({
                "success": False,
                "message": "没有上传文件"
            })

        file = request.files['maldi_image']

        if file.filename == '':
            return jsonify({
                "success": False,
                "message": "没有选择文件"
            })

        # 检查文件类型
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext not in allowed_extensions:
            return jsonify({
                "success": False,
                "message": "不支持的文件格式，请上传图片文件（png, jpg, jpeg, gif, bmp, tiff）"
            })

        # 生成唯一的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"maldi_{timestamp}_{filename}"

        # 保存文件
        upload_path = os.path.join(current_app.root_path, MALDI_UPLOAD_DIR, unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)

        # 返回文件的URL路径
        image_url = url_for('static', filename=f'maldi_uploads/{unique_filename}')

        return jsonify({
            "success": True,
            "message": "质谱图上传成功",
            "image_url": image_url,
            "filename": unique_filename
        })

    except Exception as e:
        print(f"上传MALDI质谱图失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"上传失败: {str(e)}"
        })
