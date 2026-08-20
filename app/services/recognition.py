"""vendor 专用：菌种识别管线（裁皿 → 切片选块 → 分类聚合 → 整皿覆盖）。

仅 vendor 模式导入本模块；client 模式不安装 torch/cv2，识别走我方远程 API。
"""
import os

import cv2
import numpy as np

from app.extensions import db
from app.models import BacdiveRecord, BacdiveStrainMatch, Strain
from app.services.crop_plate_batch import crop_plate
from app.services.yolo_service import (
    HWISHAI_CLASSIFIER_MODEL,
    classify_images,
    fuse_predictions,
)

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
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


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


def run_recognition(image_bytes, filename, upload_dir, result_dir, url_builder=None):
    """跑完整识别管线，返回结构化结果。

    url_builder(knowledge_record_id) -> str 或 None：由调用方决定知识库链接形态
    （vendor 网页传 url_for；远程 API 不传，只给 record_id）。
    """
    # 先解码校验，成功后才把原始文件落盘——避免"不可解码/可疑内容"被写入
    # static/uploads（filename 由调用方经 upload_guard 生成，扩展名可信）。
    q_raw = _read_image_bgr(image_bytes)
    if q_raw is None:
        return {"ok": False, "message": "图片读取失败，请更换图片重试"}

    upload_path = os.path.join(upload_dir, filename)
    with open(upload_path, "wb") as f:
        f.write(image_bytes)

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
            upload_path,
            plate_geometry=plate_geometry,
            force_slice=is_large_image,
        )
    )
    classification = selected_classification
    if classification is None:
        classifications = classify_images([detection_image])
        classification = classifications[0] if classifications else None
    if not classification or not classification.get("top3"):
        return {"ok": False, "message": "HwishAI未返回菌种候选"}

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
    if classification["top3"][0]["confidence"] < 0.4:
        low_confidence = True

    result_filename = (
        f"{os.path.splitext(filename)[0]}_classified.jpg"
    )
    result_path = os.path.join(result_dir, result_filename)
    if not cv2.imwrite(result_path, detection_image):
        return {"ok": False, "message": "识别结果图片保存失败"}

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
            "knowledge_record_id": knowledge_record_id,
            "knowledge_url": (
                url_builder(knowledge_record_id)
                if (url_builder and knowledge_record_id)
                else None
            ),
        })

    return {
        "ok": True,
        "message": "HwishAI菌种识别完成（BioCLIP + XGBoost）",
        "top_candidates": top_candidates,
        "top_detection": top_candidates[0],
        "result_path": result_path,
        "result_filename": result_filename,
        "detection_image": detection_image,
        "plate_crop": plate_crop,
        "image_selection": image_selection,
        "input_risk": input_risk,
        "low_confidence": low_confidence,
        "upload_path": upload_path,
    }
