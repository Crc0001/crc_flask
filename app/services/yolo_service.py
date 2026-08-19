from pathlib import Path
import ast
import json
import os
import threading

# 必须在 ultralytics/cv2 之前导入 torch：否则 DirectML 推理速度会慢约 6 倍
# （实测：torch 由 ultralytics 间接触发导入时，DML 每批编码 0.53s → 3.5s）
import torch

import cv2
import numpy as np
from ultralytics import YOLO

MODEL_PATH = Path(__file__).resolve().parents[1] / "weights" / "best.pt"
HWISHAI_PROJECT_PATH = Path(os.environ.get(
    "HWISHAI_PATH",
    str(Path(__file__).resolve().parents[2] / "HwishAI"),
))
# 分类器模型：默认使用新模型（bioclip_hc_euclidean_vit_b16 44类，448切片训练域，
# 训练数据为原始皿切出的 448x448 切片，预处理统一压到 224x224）。
# 需要切回旧模型（bioclip-2 + model_tuned 46类，整皿图训练域）时设置环境变量
# HWISHAI_CLASSIFIER_MODEL=model_tuned。
HWISHAI_CLASSIFIER_MODEL = os.environ.get(
    "HWISHAI_CLASSIFIER_MODEL",
    "bioclip_hc_euclidean_vit_b16",
)
HWISHAI_MODEL_DIR = HWISHAI_PROJECT_PATH / HWISHAI_CLASSIFIER_MODEL / "model"
HWISHAI_EMBEDDINGS_DIR = HWISHAI_PROJECT_PATH / HWISHAI_CLASSIFIER_MODEL / "embeddings"
HWISHAI_RESULTS_DIR = HWISHAI_PROJECT_PATH / HWISHAI_CLASSIFIER_MODEL / "results"
# 旧模型（bioclip-2 系）：与训练脚本 train_classifier.py 相同的预处理
LEGACY_MODEL_NAMES = {"model_tuned", "model"}
LEGACY_PREPROCESS = None  # 延迟导入 torchvision，避免无该依赖的老环境启动失败
LOW_MATCH_THRESHOLD = 0.5
SEMANTIC_POSITIVE_PROMPTS = (
    "a laboratory photograph of bacterial colonies growing on an agar plate",
    "a close-up scientific image of microbial colonies in a petri dish",
    "bacterial colony morphology on culture medium",
)
SEMANTIC_NEGATIVE_PROMPTS = (
    "a screenshot of a website or software interface",
    "an advertisement or product brochure with text",
    "laboratory equipment, packaging, or an instrument",
    "a document, chart, diagram, or presentation slide",
    "an ordinary non-biological photograph",
)
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
_BIOCLIP_MODEL_REF = None
_FEATURE_STATISTICS = None
_SEMANTIC_TEXT_FEATURES = None
_BIOCLIP_LOCK = threading.Lock()


def _resolve_device():
    """解析分类器计算设备：优先 DirectML（AMD 等显卡）→ CUDA → CPU。

    任何一步异常都自动回退 CPU，保证无显卡/驱动异常的老机器零风险。
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        try:
            import torch_directml
            if torch_directml.device_count() > 0:
                return torch_directml.device(0)
        except Exception:
            pass
        return "cpu"
    except Exception:
        return "cpu"


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


def _get_feature_statistics(classes):
    global _FEATURE_STATISTICS
    if _FEATURE_STATISTICS is not None:
        return _FEATURE_STATISTICS

    try:
        embeddings = np.load(
            HWISHAI_EMBEDDINGS_DIR / "embeddings.npy",
            mmap_mode="r",
        )
        record_indices = []
        true_labels = []
        for split_name in ("oof", "val", "test"):
            payload = np.load(
                HWISHAI_RESULTS_DIR / f"probabilities_{split_name}.npz",
                allow_pickle=False,
            )
            record_indices.append(payload["record_indices"])
            true_labels.append(payload["y_true"])

        record_indices = np.concatenate(record_indices).astype(np.int64)
        true_labels = np.concatenate(true_labels).astype(np.int64)
        if len(np.unique(record_indices)) != len(record_indices):
            raise ValueError("菌种特征索引存在重复")
        if record_indices.min() < 0 or record_indices.max() >= len(embeddings):
            raise ValueError("菌种特征索引超出范围")
        if true_labels.min() < 0 or true_labels.max() >= len(classes):
            raise ValueError("菌种特征标签超出范围")

        mapped_features = np.asarray(embeddings[record_indices], dtype=np.float32)
        centroids = []
        distance_distributions = []
        class_counts = []
        for class_index in range(len(classes)):
            class_features = mapped_features[true_labels == class_index]
            if not len(class_features):
                raise ValueError(f"菌种特征缺少类别索引: {class_index}")
            centroid = class_features.mean(axis=0)
            centroids.append(centroid)
            distance_distributions.append(
                np.sort(np.linalg.norm(class_features - centroid, axis=1))
            )
            class_counts.append(len(class_features))

        _FEATURE_STATISTICS = {
            "available": True,
            "centroids": np.asarray(centroids, dtype=np.float32),
            "distance_distributions": distance_distributions,
            "class_counts": np.asarray(class_counts, dtype=np.int32),
            "mapped_count": int(len(record_indices)),
        }
    except Exception as exc:
        _FEATURE_STATISTICS = {
            "available": False,
            "error": str(exc),
        }
    return _FEATURE_STATISTICS


def _get_semantic_text_features(model, device):
    global _SEMANTIC_TEXT_FEATURES
    if _SEMANTIC_TEXT_FEATURES is not None:
        return _SEMANTIC_TEXT_FEATURES

    try:
        import open_clip
        import torch
        import torch.nn.functional as F

        prompts = SEMANTIC_POSITIVE_PROMPTS + SEMANTIC_NEGATIVE_PROMPTS
        tokenizer = open_clip.get_tokenizer(_BIOCLIP_MODEL_REF)
        with torch.no_grad():
            text_features = model.encode_text(tokenizer(prompts).to(device))
            text_features = F.normalize(text_features.float(), dim=-1)
        _SEMANTIC_TEXT_FEATURES = {
            "available": True,
            "features": text_features,
            "positive_count": len(SEMANTIC_POSITIVE_PROMPTS),
        }
    except Exception as exc:
        _SEMANTIC_TEXT_FEATURES = {
            "available": False,
            "error": str(exc),
        }
    return _SEMANTIC_TEXT_FEATURES


def _feature_distance_signal(feature, class_index, statistics):
    if not statistics.get("available"):
        return {
            "available": False,
            "error": "菌种特征统计不可用",
        }

    centroid = statistics["centroids"][class_index]
    reference_distances = statistics["distance_distributions"][class_index]
    distance = float(np.linalg.norm(feature - centroid))
    percentile = float(
        np.searchsorted(reference_distances, distance, side="right")
        / len(reference_distances)
    )
    return {
        "available": True,
        "distance": round(distance, 6),
        "percentile": round(percentile, 6),
        "reference_count": int(statistics["class_counts"][class_index]),
    }


def _semantic_signal(similarities, semantic_bundle):
    if not semantic_bundle.get("available") or similarities is None:
        return {
            "available": False,
            "error": "零样本语义判断不可用",
        }

    positive_count = semantic_bundle["positive_count"]
    positive_score = float(np.max(similarities[:positive_count]))
    negative_score = float(np.max(similarities[positive_count:]))
    return {
        "available": True,
        "positive_score": round(positive_score, 6),
        "negative_score": round(negative_score, 6),
        "margin": round(positive_score - negative_score, 6),
    }


def _compose_input_risk(top_confidence, feature_signal, semantic_signal):
    probability_risk = float(np.clip((0.85 - top_confidence) / 0.85, 0.0, 1.0))
    weighted_signals = [(probability_risk, 0.30)]

    feature_percentile = None
    if feature_signal.get("available"):
        feature_percentile = float(feature_signal["percentile"])
        feature_risk = float(
            np.clip((feature_percentile - 0.75) / 0.25, 0.0, 1.0)
        )
        weighted_signals.append((feature_risk, 0.20))

    semantic_margin = None
    if semantic_signal.get("available"):
        semantic_margin = float(semantic_signal["margin"])
        semantic_risk = float(
            np.clip((-semantic_margin - 0.01) / 0.06, 0.0, 1.0)
        )
        weighted_signals.append((semantic_risk, 0.50))

    total_weight = sum(weight for _, weight in weighted_signals)
    risk_score = (
        sum(value * weight for value, weight in weighted_signals)
        / total_weight
    )
    strong_semantic_risk = (
        semantic_margin is not None and semantic_margin <= -0.06
    )

    reasons = []
    if strong_semantic_risk:
        reasons.append("图片内容更接近截图、广告、设备或文档，而非直接菌落照片")
    elif semantic_margin is not None and semantic_margin <= -0.01:
        reasons.append("图片内容与直接菌落照片的语义一致性偏弱")
    if feature_percentile is not None and feature_percentile >= 0.95:
        reasons.append("图像特征与该候选菌种的已知样本差异较大")
    if top_confidence < 0.5:
        reasons.append("Top1模型相对匹配度低于50%")

    if strong_semantic_risk or risk_score >= 0.65:
        level = "high"
        label = "高风险"
        message = (
            "输入图片可能不是直接菌落照片，以下Top3仅供参考，"
            "建议更换原始菌落图或结合MALDI-TOF、16S复核。"
        )
    elif (
        risk_score >= 0.30
        or top_confidence < 0.5
        or (feature_percentile is not None and feature_percentile >= 0.95)
        or (semantic_margin is not None and semantic_margin <= -0.01)
    ):
        level = "medium"
        label = "需复核"
        message = (
            "模型对当前图片的适用性存在不确定性，Top3可作为候选，"
            "请结合原图质量或其他检测结果复核。"
        )
    else:
        level = "low"
        label = "未见明显风险"
        message = "软风险评估未发现明显的输入适用性风险。"

    return {
        "level": level,
        "label": label,
        "score": round(float(risk_score), 6),
        "soft_only": level != "high",
        "temporary_gate": level == "high",
        "message": message,
        "reasons": reasons,
        "signals": {
            "classifier_probability": {
                "top1": round(float(top_confidence), 6),
                "risk": round(probability_risk, 6),
            },
            "feature_distance": feature_signal,
            "zero_shot_semantic": semantic_signal,
        },
    }


def _load_legacy_classifier():
    """加载原始模型：bioclip-2 编码器 + model_tuned/model 的 XGBoost（整皿图训练域）。

    预处理与训练脚本 train_classifier*.py 完全一致：
    ToTensor -> Resize(224,224) -> CLIP 归一化，特征做 L2 归一化。
    """
    global _BIOCLIP_MODEL, _BIOCLIP_XGB, _BIOCLIP_CLASSES, _BIOCLIP_DEVICE
    global _BIOCLIP_PREPROCESS, _BIOCLIP_CN_NAMES, _BIOCLIP_NORMALIZATION, _BIOCLIP_MODEL_REF
    global LEGACY_PREPROCESS

    import pickle

    import open_clip
    from torchvision import transforms
    from xgboost import XGBClassifier

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    if LEGACY_PREPROCESS is None:
        LEGACY_PREPROCESS = transforms.Compose([
            transforms.ToTensor(),
            transforms.Resize((224, 224), antialias=True),
            transforms.Normalize(
                mean=(0.48145466, 0.4578275, 0.40821073),
                std=(0.26862954, 0.26130258, 0.27577711),
            ),
        ])

    device = _resolve_device()
    model, _ = open_clip.create_model_from_pretrained(
        "hf-hub:imageomics/bioclip-2",
        device="cpu",
    )
    model = model.to(device).eval()
    print(
        f"[HwishAI] 分类器: bioclip-2 + {HWISHAI_CLASSIFIER_MODEL} @ {device}",
        flush=True,
    )

    model_dir = HWISHAI_PROJECT_PATH / HWISHAI_CLASSIFIER_MODEL
    xgb_path = model_dir / "xgb.json"
    label_path = model_dir / "label_encoder.pkl"
    if not xgb_path.exists() or not label_path.exists():
        raise FileNotFoundError(f"原始模型文件缺失(xgb.json/label_encoder.pkl): {model_dir}")

    xgb = XGBClassifier()
    xgb.load_model(str(xgb_path))
    label_encoder = pickle.load(open(label_path, "rb"))
    classes = np.asarray(label_encoder.classes_, dtype=str)
    chinese_names = _load_hwishai_chinese_names()
    if len(classes) != int(xgb.n_classes_):
        raise ValueError(
            f"原始模型标签数量({len(classes)})与XGBoost类别数({xgb.n_classes_})不一致"
        )

    _BIOCLIP_MODEL = model
    _BIOCLIP_XGB = xgb
    _BIOCLIP_CLASSES = classes
    _BIOCLIP_DEVICE = device
    _BIOCLIP_PREPROCESS = LEGACY_PREPROCESS
    _BIOCLIP_CN_NAMES = chinese_names
    _BIOCLIP_NORMALIZATION = "l2"
    _BIOCLIP_MODEL_REF = "hf-hub:imageomics/bioclip-2"
    return model, xgb, classes, device, LEGACY_PREPROCESS, chinese_names, "l2"


def _get_bioclip_classifier():
    global _BIOCLIP_MODEL, _BIOCLIP_XGB, _BIOCLIP_CLASSES
    global _BIOCLIP_DEVICE, _BIOCLIP_PREPROCESS, _BIOCLIP_CN_NAMES
    global _BIOCLIP_NORMALIZATION, _BIOCLIP_MODEL_REF

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

    # 原始模型（bioclip-2 + XGBoost，整皿图训练域）走独立加载分支
    if HWISHAI_CLASSIFIER_MODEL in LEGACY_MODEL_NAMES:
        return _load_legacy_classifier()

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

    device = _resolve_device()
    model, preprocess = open_clip.create_model_from_pretrained(
        model_id,
        device="cpu",
    )
    model = model.to(device).eval()
    print(f"[HwishAI] 分类器计算设备: {device}", flush=True)

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
    _BIOCLIP_MODEL_REF = model_id
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
        # ---- 门禁已注释（演示模式）：不再加载特征统计与语义文本特征 ----
        # feature_statistics = _get_feature_statistics(classes)
        # semantic_bundle = _get_semantic_text_features(model, device)
        feature_statistics = {"available": False}
        semantic_bundle = {"available": False}
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
                # ---- 门禁已注释（演示模式）：不再计算语义相似度 ----
                # if semantic_bundle.get("available"):
                #     semantic_similarities = (
                #         F.normalize(features.float(), dim=-1)
                #         @ semantic_bundle["features"].T
                #     ).cpu().numpy()
                # else:
                #     semantic_similarities = None
                semantic_similarities = None
            feature_rows = features.float().cpu().numpy()
            probabilities = xgb.predict_proba(feature_rows)

            for row_index, row in enumerate(probabilities):
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
                # ---- 门禁已注释（演示模式）：结果仅来自封闭分类器 + XGBoost 打分 ----
                # feature_signal = _feature_distance_signal(
                #     feature_rows[row_index],
                #     int(top_indices[0]),
                #     feature_statistics,
                # )
                # semantic_signal = _semantic_signal(
                #     (
                #         semantic_similarities[row_index]
                #         if semantic_similarities is not None
                #         else None
                #     ),
                #     semantic_bundle,
                # )
                # input_risk = _compose_input_risk(
                #     top3[0]["confidence"],
                #     feature_signal,
                #     semantic_signal,
                # )
                input_risk = {
                    "level": "low",
                    "label": "未启用",
                    "score": 0.0,
                    "soft_only": True,
                    "temporary_gate": False,
                    "message": (
                        "门禁已关闭（演示模式），Top3 直接来自封闭分类器与 XGBoost 打分。"
                    ),
                    "reasons": [],
                    "signals": {},
                }
                predictions.append({
                    "species_name": top3[0]["species_name"],
                    "confidence": top3[0]["confidence"],
                    "top3": top3,
                    "input_risk": input_risk,
                    "probabilities": [round(float(p), 6) for p in row],
                })

    return predictions


def classify_images(images_bgr):
    """Batch-classify candidate images for tile selection."""
    return _classify_images(images_bgr)


def fuse_predictions(predictions, weights):
    """按权重聚合多个预测的概率向量，返回与单预测同结构的融合结果。

    Args:
        predictions: classify_images 返回的预测列表（每个含 probabilities/top3/input_risk）
        weights: 与 predictions 等长的非负权重；权重<=0 或缺少概率向量的预测被忽略。

    Returns:
        融合后的预测 dict（input_risk 取权重最大的有效预测）；无可用预测时返回 None。
    """
    valid = [
        (pred, float(weight))
        for pred, weight in zip(predictions, weights)
        if pred and float(weight) > 0 and pred.get("probabilities")
    ]
    if not valid:
        usable = [
            (pred, float(weight))
            for pred, weight in zip(predictions, weights)
            if pred
        ]
        if not usable:
            return None
        return max(usable, key=lambda item: item[1])[0]

    vectors = np.asarray(
        [item[0]["probabilities"] for item in valid],
        dtype=np.float32,
    )
    weight_values = np.asarray([item[1] for item in valid], dtype=np.float32)
    weight_values = weight_values / weight_values.sum()
    fused_probs = (vectors * weight_values[:, None]).sum(axis=0)

    model, xgb, classes, device, preprocess, chinese_names, normalization = (
        _get_bioclip_classifier()
    )
    top_indices = np.argsort(fused_probs)[::-1][:3]
    top3 = [
        {
            "species_name": str(classes[int(index)]),
            "chinese_name": _class_chinese_name(
                str(classes[int(index)]),
                chinese_names,
            ),
            "confidence": round(float(fused_probs[int(index)]), 6),
        }
        for index in top_indices
    ]
    risk_source = max(valid, key=lambda item: item[1])[0]
    return {
        "species_name": top3[0]["species_name"],
        "confidence": top3[0]["confidence"],
        "top3": top3,
        "input_risk": risk_source.get("input_risk") or {},
        "probabilities": [round(float(p), 6) for p in fused_probs],
    }


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
