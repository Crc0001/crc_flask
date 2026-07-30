from pathlib import Path
import ast
import json
import os
import threading

import cv2
import numpy as np
from ultralytics import YOLO

MODEL_PATH = Path(__file__).resolve().parents[1] / "weights" / "best.pt"
HWISHAI_PROJECT_PATH = Path(os.environ.get(
    "HWISHAI_PATH",
    str(Path(__file__).resolve().parents[2] / "HwishAI"),
))
HWISHAI_CLASSIFIER_MODEL = os.environ.get(
    "HWISHAI_CLASSIFIER_MODEL",
    "bioclip_hc_euclidean_vit_b16",
)
HWISHAI_MODEL_DIR = HWISHAI_PROJECT_PATH / HWISHAI_CLASSIFIER_MODEL / "model"
LOW_MATCH_THRESHOLD = 0.5
CLASSIFIER_NAME_ALIASES = {
    "Faucicola osloensis": "Moraxella osloensis",
    "Staphylococcus ureilyticu": "Staphylococcus ureilyticus",
}

_MODEL = None
_BIOCLIP_MODEL = None
_BIOCLIP_XGB = None
_BIOCLIP_CLASSES = None
_BIOCLIP_DEVICE = None
_BIOCLIP_PREPROCESS = None
_BIOCLIP_CN_NAMES = None
_BIOCLIP_NORMALIZATION = None
_BIOCLIP_LOCK = threading.Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"YOLO模型文件不存在: {MODEL_PATH}")
        _MODEL = YOLO(str(MODEL_PATH))
    return _MODEL


def _load_hwishai_chinese_names():
    source_path = HWISHAI_PROJECT_PATH / "add_cn_names.py"
    if not source_path.exists():
        return {}

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "CN" for target in node.targets):
            names = ast.literal_eval(node.value)
            if isinstance(names, dict):
                return {str(key): str(value) for key, value in names.items()}
    return {}


def _class_chinese_name(species_name, chinese_names):
    canonical_name = CLASSIFIER_NAME_ALIASES.get(species_name, species_name)
    return chinese_names.get(species_name) or chinese_names.get(canonical_name) or ""

def _get_bioclip_classifier():
    global _BIOCLIP_MODEL, _BIOCLIP_XGB, _BIOCLIP_CLASSES
    global _BIOCLIP_DEVICE, _BIOCLIP_PREPROCESS, _BIOCLIP_CN_NAMES
    global _BIOCLIP_NORMALIZATION

    if _BIOCLIP_MODEL is not None:
        return (
            _BIOCLIP_MODEL,
            _BIOCLIP_XGB,
            _BIOCLIP_CLASSES,
            _BIOCLIP_DEVICE,
            _BIOCLIP_PREPROCESS,
            _BIOCLIP_CN_NAMES,
            _BIOCLIP_NORMALIZATION,
        )

    metadata_path = HWISHAI_MODEL_DIR / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"HwishAI模型元数据不存在: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    classes = np.asarray(metadata.get("classes") or [], dtype=str)
    model_id = metadata.get("encoder", {}).get("model_ref")
    normalization = metadata.get("encoder", {}).get(
        "embedding_normalization",
        "raw",
    )
    class_count = int(metadata.get("class_count") or len(classes))
    xgb_path = HWISHAI_MODEL_DIR / f"xgb_{class_count}.json"
    if not xgb_path.exists():
        candidates = list(HWISHAI_MODEL_DIR.glob("xgb*.json"))
        if len(candidates) != 1:
            raise FileNotFoundError(f"HwishAI XGBoost模型无法确定: {HWISHAI_MODEL_DIR}")
        xgb_path = candidates[0]
    if not model_id or len(classes) != class_count:
        raise ValueError(f"HwishAI模型元数据不完整或类别数量不一致: {metadata_path}")
    if normalization not in {"raw", "l2"}:
        raise ValueError(f"不支持的特征归一化方式: {normalization}")

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    import open_clip
    import torch
    from xgboost import XGBClassifier

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = open_clip.create_model_from_pretrained(
        model_id,
        device=device,
    )
    model = model.to(device).eval()

    xgb = XGBClassifier()
    xgb.load_model(str(xgb_path))
    chinese_names = _load_hwishai_chinese_names()
    if len(classes) != int(xgb.n_classes_):
        raise ValueError(
            f"HwishAI标签数量({len(classes)})与XGBoost类别数({xgb.n_classes_})不一致"
        )


    _BIOCLIP_MODEL = model
    _BIOCLIP_XGB = xgb
    _BIOCLIP_CLASSES = classes
    _BIOCLIP_DEVICE = device
    _BIOCLIP_PREPROCESS = preprocess
    _BIOCLIP_CN_NAMES = chinese_names
    _BIOCLIP_NORMALIZATION = normalization
    return model, xgb, classes, device, preprocess, chinese_names, normalization


def _classify_images(images_bgr):
    if not images_bgr:
        return []

    import torch
    import torch.nn.functional as F
    from PIL import Image

    predictions = []

    with _BIOCLIP_LOCK:
        model, xgb, classes, device, preprocess, chinese_names, normalization = _get_bioclip_classifier()
        for start in range(0, len(images_bgr), 16):
            image_batch = images_bgr[start:start + 16]
            tensors = [
                preprocess(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
                for image in image_batch
            ]
            batch = torch.stack(tensors).to(device)
            with torch.no_grad():
                features = model.encode_image(batch)
                if normalization == "l2":
                    features = F.normalize(features, dim=-1)
            probabilities = xgb.predict_proba(features.cpu().numpy())

            for row in probabilities:
                top_indices = np.argsort(row)[::-1][:3]
                top3 = [
                    {
                        "species_name": str(classes[int(index)]),
                        "chinese_name": _class_chinese_name(
                            str(classes[int(index)]),
                            chinese_names,
                        ),
                        "confidence": round(float(row[int(index)]), 6),
                    }
                    for index in top_indices
                ]
                predictions.append({
                    "species_name": top3[0]["species_name"],
                    "confidence": top3[0]["confidence"],
                    "top3": top3,
                })

    return predictions


def classify_images(images_bgr):
    """Batch-classify candidate images for tile selection."""
    return _classify_images(images_bgr)


def _normalize_scientific_name(value):
    return " ".join(str(value or "").split()).casefold()


def _match_classifier_label(species_name, strain_candidates):
    normalized = _normalize_scientific_name(CLASSIFIER_NAME_ALIASES.get(species_name, species_name))
    for strain in strain_candidates or []:
        if _normalize_scientific_name(strain.get("scientific_name")) == normalized:
            return strain
    return None


def detect_and_draw(
    image_path,
    save_dir,
    confidence_threshold=0.5,
    strain_candidates=None,
    image_bgr=None,
    image_classification=None,
):

    # 1. 验证并读取待检测图像
    if image_bgr is None and not os.path.exists(image_path):
        return {
            "success": False,
            "error": f"图像文件不存在: {image_path}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": None,
            "inference_time": None
        }

    # 2. 读取图像
    try:
        img = image_bgr.copy() if image_bgr is not None else cv2.imread(image_path)
        if img is None:
            return {
                "success": False,
                "error": "无法读取图像文件，可能格式不支持或文件损坏",
                "detections": None,
                "result_path": None,
                "detect_count": 0,
                "image_size": None,
                "inference_time": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"读取图像时出错: {str(e)}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": None,
            "inference_time": None
        }

    # 3. 获取图像尺寸
    img_height, img_width = img.shape[:2]

    # 4. 执行检测
    try:
        results = _get_model()(img, conf=confidence_threshold)[0]
        inference_time = results.speed  # 获取推理时间（毫秒）
    except Exception as e:
        return {
            "success": False,
            "error": f"YOLO框选失败: {str(e)}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": (img_width, img_height),
            "inference_time": None
        }

    # 5. YOLO定位菌落，HwishAI增强模型识别预处理后的整图
    detections = []
    pending_boxes = []

    if results.boxes is not None and len(results.boxes) > 0:
        for box in results.boxes:
            detector_confidence = float(box.conf[0])
            if detector_confidence < confidence_threshold:
                continue

            class_id = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1 = max(0, min(x1, img_width - 1))
            y1 = max(0, min(y1, img_height - 1))
            x2 = max(x1 + 1, min(x2, img_width))
            y2 = max(y1 + 1, min(y2, img_height))


            pending_boxes.append({
                "class_id": class_id,
                "detector_name": results.names[class_id],
                "detector_confidence": detector_confidence,
                "bbox": [x1, y1, x2, y2],
            })

    try:
        if image_classification is None:
            image_classification = _classify_images([img])[0]
        classifications = [image_classification] * len(pending_boxes)
    except Exception as exc:
        return {
            "success": False,
            "error": f"HwishAI菌种识别失败: {exc}",
            "detections": None,
            "result_path": None,
            "detect_count": 0,
            "image_size": (img_width, img_height),
            "inference_time": inference_time,
        }

    for box_data, classification in zip(pending_boxes, classifications):
        x1, y1, x2, y2 = box_data["bbox"]
        species_name = classification["species_name"]
        classifier_confidence = float(classification["confidence"])
        strain = _match_classifier_label(species_name, strain_candidates)
        classifier_chinese_name = classification["top3"][0].get("chinese_name", "")
        matched_strain_name = (
            strain.get("strain_name")
            if strain
            else classifier_chinese_name or species_name
        )
        matched_strain_id = strain.get("strain_id") if strain else None
        low_confidence = classifier_confidence < LOW_MATCH_THRESHOLD
        box_color = (0, 0, 255) if low_confidence else (0, 255, 0)

        detection_info = {
            "name": box_data["detector_name"],
            "class_id": box_data["class_id"],
            "confidence": box_data["detector_confidence"],
            "bbox": [x1, y1, x2, y2],
            "bbox_norm": [
                x1 / img_width,
                y1 / img_height,
                x2 / img_width,
                y2 / img_height,
            ],
            "bbox_center": [(x1 + x2) // 2, (y1 + y2) // 2],
            "bbox_size": [x2 - x1, y2 - y1],
            "match_score": round(classifier_confidence, 6),
            "image_score": round(classifier_confidence, 6),
            "feature_score": round(classifier_confidence, 6),
            "edge_score": 0.0,
            "low_confidence": low_confidence,
            "matched_strain_id": matched_strain_id,
            "matched_strain_name": matched_strain_name,
            "matched_image_path": "",
            "recognition_model": f"HwishAI {HWISHAI_CLASSIFIER_MODEL}",
            "classifier_species_name": species_name,
            "classifier_chinese_name": classifier_chinese_name,
            "classifier_confidence": round(classifier_confidence, 6),
            "classifier_top3": classification["top3"],
            "classification_scope": "preprocessed_image",
        }
        detections.append(detection_info)

        label_name = species_name[:32]
        label = f"{label_name} {classifier_confidence * 100:.0f}%"
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
        )
        label_y1 = max(0, y1 - text_height - baseline - 5)
        cv2.rectangle(img, (x1, y1), (x2, y2), box_color, 2)
        cv2.rectangle(
            img,
            (x1, label_y1),
            (min(img_width - 1, x1 + text_width), y1),
            box_color,
            -1,
        )
        cv2.putText(
            img,
            label,
            (x1, max(text_height, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            2,
        )

    # 6. 保存结果图像
    os.makedirs(save_dir, exist_ok=True)
    result_filename = f"{os.path.basename(image_path)}"
    result_path = os.path.join(save_dir, result_filename)

    try:
        cv2.imwrite(result_path, img)

    except Exception as e:
        return {
            "success": False,
            "error": f"保存结果图像时出错: {str(e)}",
            "detections": detections if detections else None,
            "result_path": None,
            "detect_count": len(detections),
            "image_size": (img_width, img_height),
            "inference_time": inference_time
        }

    # 7. 整理返回结果
    response = {
        "success": True,
        "error": None,
        "detections": detections if detections else None,  # 空列表时返回None
        "result_path": result_path,
        "detect_count": len(detections),
        "image_size": (img_width, img_height),
        "inference_time": inference_time,  # 包含预处理、推理、后处理时间
        "confidence_threshold": confidence_threshold,
        "has_detections": len(detections) > 0,
        "classification": image_classification,
        "recommended_strain_name": (
            detections[0]["matched_strain_name"]
            if detections
            else image_classification["top3"][0].get("chinese_name")
            or image_classification["species_name"]
        ),
        "recommended_match_score": image_classification["confidence"],
    }

    return response
