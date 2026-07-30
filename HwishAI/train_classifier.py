# -*- coding: utf-8 -*-
"""
BioCLIP + XGBoost classifier (open_clip direct, no torch.compile)

BioCLIP = spectrophotometer -> 768D features
XGBoost = calibration curve -> features -> species

Usage: python train_classifier.py train              # 增量训练（默认）
       python train_classifier.py train --reset      # 从头训练（清空旧库）
       python train_classifier.py predict photo.jpg  # 预测
"""
import argparse, json, os, pickle, sys
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

WORK_DIR = Path(__file__).parent
TRAIN_DIR = WORK_DIR / "train"
MODEL_DIR = WORK_DIR / "model"
MODEL_DIR.mkdir(exist_ok=True)

# BioCLIP image preprocessing (from bioclip source)
PREPROCESS = transforms.Compose([
    transforms.ToTensor(),
    transforms.Resize((224, 224), antialias=True),
    transforms.Normalize(
        mean=(0.48145466, 0.4578275, 0.40821073),
        std=(0.26862954, 0.26130258, 0.27577711),
    ),
])

MODEL_STR = "hf-hub:imageomics/bioclip-2"


# ============================================================
# 数据库持久化（增量训练的核心）
# ============================================================

def load_existing_db():
    """加载已有的特征库（如果存在）。返回 (X, y, paths) 或 (None, None, [])"""
    emb_path = MODEL_DIR / "embeddings.npy"
    lbl_path = MODEL_DIR / "labels.npy"
    pth_path = MODEL_DIR / "paths.json"
    if emb_path.exists() and lbl_path.exists() and pth_path.exists():
        X_old = np.load(emb_path)
        y_old = np.load(lbl_path)
        paths_old = json.load(open(pth_path, "r", encoding="utf-8"))
        print(f"[数据库] 已加载 {len(paths_old)} 条已有特征记录")
        return X_old, y_old, paths_old
    return None, None, []


def save_db(X, y, paths):
    """保存特征库到 model/ 目录"""
    np.save(MODEL_DIR / "embeddings.npy", X)
    np.save(MODEL_DIR / "labels.npy", y)
    json.dump(paths, open(MODEL_DIR / "paths.json", "w"), ensure_ascii=False, indent=2)
    print(f"[数据库] 已保存 {len(paths)} 条特征记录 -> {MODEL_DIR}")


def show_db_summary():
    """打印当前数据库概况"""
    X_old, y_old, paths_old = load_existing_db()
    if X_old is None:
        print("[数据库] 空（尚未训练过）")
        return
    unique_species = sorted(set(y_old))
    print(f"\n[数据库概况] {len(paths_old)} 张图片，{len(unique_species)} 个物种：")
    for sp in unique_species:
        count = (y_old == sp).sum()
        print(f"    {sp}: {count} 张")


# ============================================================
# BioCLIP 编码器
# ============================================================

class BioCLIPEncoder:
    def __init__(self, device="cpu"):
        import open_clip
        print(f"[Device] {device}")
        print("[Loading] BioCLIP model from HF Hub (cached)...")
        model, _ = open_clip.create_model_from_pretrained(
            MODEL_STR, device=device
        )
        model = model.to(device)
        model.eval()
        self.model = model
        self.device = device
        self.img_size = 768
        print("[OK] BioCLIP loaded")

    @torch.no_grad()
    def encode(self, image_path: str) -> np.ndarray:
        img = Image.open(image_path).convert("RGB")
        tensor = PREPROCESS(img).unsqueeze(0).to(self.device)
        features = self.model.encode_image(tensor)
        features = F.normalize(features, dim=-1)
        return features.cpu().numpy().flatten()


# ============================================================
# 特征提取（支持跳过已有图片）
# ============================================================

def build_embeddings(encoder, skip_paths=None):
    """从 train/ 提取特征。skip_paths 为已存在路径集合，这些图片会被跳过。"""
    skip_set = set(skip_paths) if skip_paths else set()

    print(f"\n=== Step 1: BioCLIP 特征提取 ===")
    class_dirs = sorted([d for d in TRAIN_DIR.iterdir() if d.is_dir()])
    if not class_dirs:
        if skip_set:
            print(f"[INFO] train/ 目录下无物种子目录，数据库已有 {len(skip_set)} 条记录，跳过特征提取。")
            return None, None, None, 0
        print(f"[ERROR] train/ 目录下没有物种子目录，且数据库为空: {TRAIN_DIR}")
        sys.exit(1)

    # 统计
    total_new = 0
    total_skip = 0
    for d in class_dirs:
        imgs = [p for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp")
                for p in d.glob(ext)]
        new = sum(1 for p in imgs if str(p) not in skip_set)
        skipped = len(imgs) - new
        tag = f" (+{new} 新" + (f", 跳过 {skipped}" if skipped else "") + ")"
        print(f"  {d.name}: {len(imgs)} 张{tag}")
        total_new += new
        total_skip += skipped

    if total_new == 0:
        print(f"\n[INFO] 无新图片（{total_skip} 张全部已入库），跳过特征提取。")
        return None, None, None, 0

    print(f"\n  总计: {total_new} 张新图片待提取, {total_skip} 张已跳过")

    embeddings, labels, paths_new = [], [], []
    done = 0
    for cd in class_dirs:
        imgs = sorted([p for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp")
                       for p in cd.glob(ext)])
        new_imgs = [p for p in imgs if str(p) not in skip_set]
        if not new_imgs:
            continue
        print(f"\n  [{cd.name}] 处理 {len(new_imgs)} 张新图片...")
        for p in new_imgs:
            try:
                emb = encoder.encode(p)
                embeddings.append(emb)
                labels.append(cd.name)
                paths_new.append(str(p))
                done += 1
                print(f"    {done}/{total_new} {p.name}", flush=True)
            except Exception as e:
                done += 1
                print(f"    {done}/{total_new} FAIL {p.name}: {e}", flush=True)

    X_new = np.array(embeddings) if embeddings else np.array([]).reshape(0, 0)
    y_new = np.array(labels)
    print(f"\n[OK] 新提取 {X_new.shape[0]} 张图片 x 768d 特征")
    return X_new, y_new, paths_new, total_new


# ============================================================
# XGBoost 训练
# ============================================================

def train(X, y):
    print(f"\n=== Step 2: XGBoost 训练 ===")
    le = LabelEncoder()
    yi = le.fit_transform(y)
    n_cls, n_samp = len(le.classes_), len(X)
    print(f"  物种: {n_cls} | 样本: {n_samp} | 维度: {X.shape[1]}")
    for i, c in enumerate(le.classes_):
        print(f"    [{i}] {c}: {(yi == i).sum()} 张")

    xgb = XGBClassifier(
        n_estimators=100, max_depth=3 if n_samp < 200 else 5,
        learning_rate=0.1,
        objective="multi:softprob" if n_cls > 2 else "binary:logistic",
        eval_metric="mlogloss" if n_cls > 2 else "logloss",
        random_state=42, verbosity=1,
    )
    xgb.fit(X, yi)
    acc = xgb.score(X, yi)
    print(f"\n  训练集准确率: {acc*100:.1f}%")

    imp = xgb.feature_importances_
    for r, d in enumerate(np.argsort(imp)[::-1][:10], 1):
        print(f"    {r}. dim{d:4d} importance={imp[d]:.4f}")
    return xgb, le


# ============================================================
# 预测
# ============================================================

def predict(img_path, encoder, xgb, le):
    img_path = Path(img_path)
    if img_path.is_dir():
        print(f"[ERROR] '{img_path}' 是一个文件夹，不是图片文件。")
        print(f"  批量测试请使用: python test_classifier.py {img_path}")
        return
    if not img_path.is_file():
        print(f"[ERROR] 文件不存在: {img_path}")
        return
    print(f"\n=== 预测: {img_path.name} ===")
    emb = encoder.encode(img_path).reshape(1, -1)
    probs = xgb.predict_proba(emb)[0]
    for r, i in enumerate(np.argsort(probs)[::-1][:5], 1):
        p = probs[i] * 100
        print(f"  {r}. {le.classes_[i]:<30s} {p:5.1f}%  [{'#'*int(p/2)}{'-'*(50-int(p/2))}]")
    c = float(probs[np.argmax(probs)])
    print(f"\n  置信度: {c*100:.1f}%", end="")
    if c >= 0.85: print(" → 直接报告")
    elif c >= 0.50: print(" → 人工复核")
    else: print(" → 建议 MALDI-TOF")


# ============================================================
# 主流程
# ============================================================

def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd")
    tr = s.add_parser("train")
    tr.add_argument("--reset", action="store_true", help="清空旧数据库，从头训练")
    pr = s.add_parser("predict"); pr.add_argument("image")
    a = p.parse_args()

    # 无参数运行时（如 IDLE F5），交互式选择模式
    if a.cmd is None:
        print("=" * 50)
        print("  BioCLIP + XGBoost 微生物图像分类器")
        print("=" * 50)
        show_db_summary()
        print("\n" + "-" * 50)
        print("  [1] 增量训练（追加新物种/新图片到数据库）")
        print("  [2] 从头训练（清空数据库，仅用 train/ 当前内容）")
        print("  [3] 预测图片")
        print("  [0] 退出")
        print("-" * 50)
        try:
            choice = input("请选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT]")
            return
        if choice == "1":
            a.cmd = "train"
            a.reset = False
        elif choice == "2":
            a.cmd = "train"
            a.reset = True
        elif choice == "3":
            img = input("请输入图片路径: ").strip()
            if not img:
                print("[ERROR] 未输入图片路径")
                return
            a.cmd = "predict"
            a.image = img
        else:
            print("[EXIT]")
            return

    if a.cmd == "train":
        device = "cuda" if torch.cuda.is_available() else "cpu"

        # ---- 增量模式：加载旧库 ----
        if a.reset:
            print("[模式] 从头训练（清空旧数据库）")
            X_old, y_old, paths_old = None, None, []
        else:
            print("[模式] 增量训练（追加到现有数据库）")
            X_old, y_old, paths_old = load_existing_db()
            if X_old is None:
                print("[INFO] 数据库为空，本次等同从头训练。")

        # ---- 提取新图片特征 ----
        enc = BioCLIPEncoder(device)
        X_new, y_new, paths_new, n_new = build_embeddings(enc, skip_paths=paths_old)

        if n_new == 0 and X_old is not None:
            # 无新图片，但用现有数据库重建模型（确保 label_encoder 与数据库一致）
            print("\n[INFO] 无新图片，从现有数据库重建模型...")

        if X_new is None or X_new.shape[0] == 0:
            if X_old is None:
                print("[ERROR] 没有可用的特征数据")
                sys.exit(1)
            # 有旧库但无新图：直接用旧库重训
            X_all, y_all, paths_all = X_old, y_old, paths_old
            print(f"[重建] 数据库 {len(paths_all)} 张, {len(set(y_all))} 种 → 正在同步模型...")
        elif X_old is not None:
            # 合并新旧数据
            X_all = np.vstack([X_old, X_new])
            y_all = np.concatenate([y_old, y_new])
            paths_all = paths_old + paths_new
        else:
            X_all, y_all, paths_all = X_new, y_new, paths_new

        print(f"\n[合并后] 共 {len(paths_all)} 张图片，{len(set(y_all))} 个物种")

        # ---- 保存数据库 ----
        save_db(X_all, y_all, paths_all)

        # ---- 训练分类器 ----
        xgb, le = train(X_all, y_all)
        xgb.save_model(str(MODEL_DIR / "xgb.json"))
        pickle.dump(le, open(MODEL_DIR / "label_encoder.pkl", "wb"))
        print(f"\n[DONE] 模型已保存到 {MODEL_DIR}")

    elif a.cmd == "predict":
        if not (MODEL_DIR / "xgb.json").exists():
            print("[ERROR] 尚无模型。请先运行训练。")
            sys.exit(1)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        enc = BioCLIPEncoder(device)
        xgb = XGBClassifier()
        xgb.load_model(str(MODEL_DIR / "xgb.json"))
        le = pickle.load(open(MODEL_DIR / "label_encoder.pkl", "rb"))
        predict(a.image, enc, xgb, le)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
