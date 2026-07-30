# -*- coding: utf-8 -*-
"""
BioCLIP + XGBoost 调参版 (正则化 + 留出验证 + Early Stopping)

与原版对比:
  - 原版: max_depth=5, 无正则化, 全量训练, 只报告训练集准确率
  - 调参版: max_depth=3, L1+L2, 15%留出验证, Early Stopping, 报告训练/验证双准确率

Usage: python train_classifier_tuned.py train            # 增量训练
       python train_classifier_tuned.py train --reset    # 从头训练
       python train_classifier_tuned.py predict photo.jpg
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
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

WORK_DIR = Path(__file__).parent
TRAIN_DIR = WORK_DIR / "train"
MODEL_DIR = WORK_DIR / "model_tuned"      # 独立目录, 不覆盖原版模型
MODEL_DIR.mkdir(exist_ok=True)

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
# 数据库持久化 (与原版兼容, 共享 model/ 特征库)
# ============================================================

ORIG_MODEL_DIR = WORK_DIR / "model"

def load_existing_db():
    emb_path = ORIG_MODEL_DIR / "embeddings.npy"
    lbl_path = ORIG_MODEL_DIR / "labels.npy"
    pth_path = ORIG_MODEL_DIR / "paths.json"
    if emb_path.exists() and lbl_path.exists() and pth_path.exists():
        X_old = np.load(emb_path)
        y_old = np.load(lbl_path)
        paths_old = json.load(open(pth_path, "r", encoding="utf-8"))
        print(f"[数据库] 已加载 {len(paths_old)} 条已有特征记录")
        return X_old, y_old, paths_old
    return None, None, []


def save_db(X, y, paths):
    np.save(ORIG_MODEL_DIR / "embeddings.npy", X)
    np.save(ORIG_MODEL_DIR / "labels.npy", y)
    json.dump(paths, open(ORIG_MODEL_DIR / "paths.json", "w"), ensure_ascii=False, indent=2)
    print(f"[数据库] 已保存 {len(paths)} 条特征记录")


def show_db_summary():
    X_old, y_old, paths_old = load_existing_db()
    if X_old is None:
        print("[数据库] 空（尚未训练过）")
        return
    unique_species = sorted(set(y_old))
    print(f"\n[数据库概况] {len(paths_old)} 张图片，{len(unique_species)} 个物种")
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
        print("[Loading] BioCLIP model...")
        model, _ = open_clip.create_model_from_pretrained(MODEL_STR, device=device)
        model = model.to(device).eval()
        self.model = model
        self.device = device
        print("[OK] BioCLIP loaded")

    @torch.no_grad()
    def encode(self, image_path: str) -> np.ndarray:
        img = Image.open(image_path).convert("RGB")
        tensor = PREPROCESS(img).unsqueeze(0).to(self.device)
        features = self.model.encode_image(tensor)
        features = F.normalize(features, dim=-1)
        return features.cpu().numpy().flatten()


# ============================================================
# 特征提取 (与原版一致)
# ============================================================

def build_embeddings(encoder, skip_paths=None):
    skip_set = set(skip_paths) if skip_paths else set()
    print(f"\n=== Step 1: BioCLIP 特征提取 ===")
    class_dirs = sorted([d for d in TRAIN_DIR.iterdir() if d.is_dir()])
    if not class_dirs:
        if skip_set:
            print(f"[INFO] train/ 下无子目录，数据库已有 {len(skip_set)} 条记录，跳过。")
            return None, None, None, 0
        print(f"[ERROR] train/ 下无子目录: {TRAIN_DIR}")
        sys.exit(1)

    total_new = 0
    for d in class_dirs:
        imgs = [p for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp") for p in d.glob(ext)]
        new = sum(1 for p in imgs if str(p) not in skip_set)
        skipped = len(imgs) - new
        print(f"  {d.name}: {len(imgs)} 张 (+{new} 新" + (f", 跳过 {skipped}" if skipped else "") + ")")
        total_new += new

    if total_new == 0:
        print(f"\n[INFO] 无新图片，跳过特征提取。")
        return None, None, None, 0

    print(f"\n  总计: {total_new} 张新图片待提取")
    embeddings, labels, paths_new = [], [], []
    done = 0
    for cd in class_dirs:
        imgs = sorted([p for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp") for p in cd.glob(ext)])
        new_imgs = [p for p in imgs if str(p) not in skip_set]
        if not new_imgs:
            continue
        print(f"\n  [{cd.name}] 处理 {len(new_imgs)} 张...")
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
    print(f"\n[OK] 新提取 {X_new.shape[0]} 张 x 768d")
    return X_new, y_new, paths_new, total_new


# ============================================================
# XGBoost 训练 — 调参版
# ============================================================

def train_tuned(X, y):
    """
    正则化 + 留出验证 + Early Stopping 版训练。
    返回 (xgb, le, train_acc, val_acc)
    """
    le = LabelEncoder()
    yi = le.fit_transform(y)
    n_cls, n_samp = len(le.classes_), len(X)
    n_species_train = len(set(y))

    print(f"\n=== Step 2: XGBoost 训练 (TUNED) ===")
    print(f"  物种: {n_cls} | 样本: {n_samp} | 维度: {X.shape[1]}")
    for i, c in enumerate(le.classes_):
        count = (yi == i).sum()
        print(f"    [{i}] {c}: {count} 张")

    # ---- 分层留出 15% 验证集 ----
    valid_size = max(0.15, 1.0 / n_samp * 10)  # 最少 10 张
    try:
        X_train, X_val, y_train, y_val = train_test_split(
            X, yi, test_size=valid_size, random_state=42, stratify=yi
        )
    except ValueError:
        # 有些种类只有 1 张图, stratify 会失败
        X_train, X_val, y_train, y_val = train_test_split(
            X, yi, test_size=valid_size, random_state=42
        )

    print(f"\n  训练集: {len(X_train)} 张 | 验证集: {len(X_val)} 张 (留出比 {len(X_val)/len(X)*100:.0f}%)")

    # ---- 调参版 XGBoost ----
    xgb = XGBClassifier(
        # 树结构 (降低单棵树复杂度)
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        min_child_weight=3,

        # 随机采样 (打破批次特征集中利用)
        subsample=0.7,
        colsample_bytree=0.5,

        # 正则化 (压制噪声维度)
        reg_alpha=0.3,      # L1
        reg_lambda=2.0,     # L2

        # Early stopping
        early_stopping_rounds=20,

        objective="multi:softprob" if n_cls > 2 else "binary:logistic",
        eval_metric="mlogloss" if n_cls > 2 else "logloss",
        random_state=42,
        verbosity=0,
    )

    print(f"\n  开始训练 (early_stopping_rounds=20)...")
    xgb.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_val, y_val)],
        verbose=False,
    )

    # ---- 评估 ----
    train_acc = xgb.score(X_train, y_train)
    val_acc = xgb.score(X_val, y_val)
    gap = (train_acc - val_acc) * 100

    print(f"\n  {'='*50}")
    print(f"  训练集准确率: {train_acc*100:.1f}%")
    print(f"  验证集准确率: {val_acc*100:.1f}%")
    print(f"  过拟合差距:   {gap:.1f} 个百分点")
    if gap < 10:
        print(f"  评估: [GOOD] 差距小, 泛化良好")
    elif gap < 20:
        print(f"  评估: [OK] 存在一定过拟合, 可接受")
    else:
        print(f"  评估: [WARN] 差距偏大, 建议补数据或增强正则化")
    print(f"  {'='*50}")

    # 最佳迭代轮数
    best_iter = xgb.best_iteration if xgb.best_iteration else xgb.n_estimators
    print(f"\n  最佳迭代轮数: {best_iter}/{xgb.n_estimators}")

    # 特征重要性 (Top-10)
    imp = xgb.feature_importances_
    print(f"\n  Top-10 特征维度:")
    for r, d in enumerate(np.argsort(imp)[::-1][:10], 1):
        print(f"    {r}. dim{d:4d} importance={imp[d]:.4f}")

    return xgb, le, train_acc, val_acc


# ============================================================
# 预测 (与原版一致)
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
        bar = '#' * int(p / 2) + '-' * (50 - int(p / 2))
        print(f"  {r}. {le.classes_[i]:<30s} {p:5.1f}%  [{bar}]")
    c = float(probs[np.argmax(probs)])
    print(f"\n  置信度: {c*100:.1f}%", end="")
    if c >= 0.85: print(" -> 直接报告")
    elif c >= 0.50: print(" -> 人工复核")
    else: print(" -> 建议 MALDI-TOF")


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

    if a.cmd is None:
        print("=" * 55)
        print("  BioCLIP + XGBoost 调参版 (正则化 + 验证集)")
        print("=" * 55)
        show_db_summary()
        print("\n" + "-" * 55)
        print("  [1] 增量训练 (调参版)")
        print("  [2] 从头训练 (清空数据库)")
        print("  [3] 预测图片")
        print("  [0] 退出")
        print("-" * 55)
        try:
            choice = input("请选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT]")
            return
        if choice == "1":
            a.cmd = "train"; a.reset = False
        elif choice == "2":
            a.cmd = "train"; a.reset = True
        elif choice == "3":
            img = input("请输入图片路径: ").strip()
            if not img:
                print("[ERROR] 未输入图片路径"); return
            a.cmd = "predict"; a.image = img
        else:
            print("[EXIT]"); return

    if a.cmd == "train":
        device = "cuda" if torch.cuda.is_available() else "cpu"

        if a.reset:
            print("[模式] 从头训练（清空旧数据库）")
            X_old, y_old, paths_old = None, None, []
        else:
            print("[模式] 增量训练（追加到现有数据库）")
            X_old, y_old, paths_old = load_existing_db()
            if X_old is None:
                print("[INFO] 数据库为空，等同从头训练。")

        enc = BioCLIPEncoder(device)
        X_new, y_new, paths_new, n_new = build_embeddings(enc, skip_paths=paths_old)

        if n_new == 0 and X_old is not None:
            print("\n[INFO] 无新图片，从现有数据库重建模型（调参版）...")

        if X_new is None or X_new.shape[0] == 0:
            if X_old is None:
                print("[ERROR] 没有可用的特征数据"); sys.exit(1)
            X_all, y_all, paths_all = X_old, y_old, paths_old
            print(f"[重建] 数据库 {len(paths_all)} 张, {len(set(y_all))} 种")
        elif X_old is not None:
            X_all = np.vstack([X_old, X_new])
            y_all = np.concatenate([y_old, y_new])
            paths_all = paths_old + paths_new
        else:
            X_all, y_all, paths_all = X_new, y_new, paths_new

        print(f"\n[合并后] 共 {len(paths_all)} 张图片，{len(set(y_all))} 个物种")

        save_db(X_all, y_all, paths_all)

        # 调参版训练
        xgb, le, train_acc, val_acc = train_tuned(X_all, y_all)

        # 保存到独立目录
        xgb.save_model(str(MODEL_DIR / "xgb.json"))
        pickle.dump(le, open(MODEL_DIR / "label_encoder.pkl", "wb"))
        print(f"\n[DONE] 调参版模型已保存到 {MODEL_DIR}")

        # 保存训练指标
        metrics = {
            "n_samples": len(X_all),
            "n_species": len(le.classes_),
            "train_accuracy": round(train_acc * 100, 2),
            "val_accuracy": round(val_acc * 100, 2),
            "overfit_gap": round((train_acc - val_acc) * 100, 2),
        }
        json.dump(metrics, open(MODEL_DIR / "metrics.json", "w"),
                  ensure_ascii=False, indent=2)
        print(f"  训练指标已保存到 {MODEL_DIR / 'metrics.json'}")

    elif a.cmd == "predict":
        model_dir = MODEL_DIR
        if not (model_dir / "xgb.json").exists():
            print("[ERROR] 尚无调参版模型。请先运行训练。")
            sys.exit(1)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        enc = BioCLIPEncoder(device)
        xgb = XGBClassifier()
        xgb.load_model(str(model_dir / "xgb.json"))
        le = pickle.load(open(model_dir / "label_encoder.pkl", "rb"))
        predict(a.image, enc, xgb, le)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
