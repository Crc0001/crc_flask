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
                # 结果仅来自封闭分类器 + XGBoost 打分（输入有效性门禁为演示模式占位）
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


