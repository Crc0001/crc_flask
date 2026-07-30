# -*- coding: utf-8 -*-
"""
批量测试脚本 — 子目录模式（文件夹名=正确答案）
用法: python batch_test.py
"""
import os, sys
from pathlib import Path
from collections import defaultdict

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from xgboost import XGBClassifier
import pickle
import open_clip

# === 配置 ===
SCRIPT_DIR = Path(__file__).parent.resolve()
TEST_DIR = SCRIPT_DIR / "test"
MODEL_DIR = SCRIPT_DIR / "model_tuned"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
EXT = {".jpg", ".jpeg", ".png", ".bmp"}

PREPROCESS = transforms.Compose([
    transforms.ToTensor(),
    transforms.Resize((224, 224), antialias=True),
    transforms.Normalize(
        mean=(0.48145466, 0.4578275, 0.40821073),
        std=(0.26862954, 0.26130258, 0.27577711),
    ),
])


def load_model():
    print(f"[1/3] 加载 BioCLIP ({DEVICE})...")
    model, _ = open_clip.create_model_from_pretrained(
        "hf-hub:imageomics/bioclip-2", device=DEVICE)
    model = model.to(DEVICE).eval()

    print(f"[2/3] 加载 XGBoost 模型...")
    xgb = XGBClassifier()
    xgb.load_model(str(MODEL_DIR / "xgb.json"))
    le = pickle.load(open(MODEL_DIR / "label_encoder.pkl", "rb"))
    print(f"       物种数: {len(le.classes_)}")

    return model, xgb, le


@torch.no_grad()
def encode(image_path, model):
    img = Image.open(image_path).convert("RGB")
    tensor = PREPROCESS(img).unsqueeze(0).to(DEVICE)
    features = model.encode_image(tensor)
    features = F.normalize(features, dim=-1)
    return features.cpu().numpy().flatten()


def collect_test_images():
    """从 test/ 子目录收集图片 (子目录名=标签)"""
    samples = []
    for sd in sorted(TEST_DIR.iterdir()):
        if not sd.is_dir():
            continue
        label = sd.name
        for f in sorted(sd.iterdir()):
            if f.suffix.lower() in EXT and f.is_file():
                samples.append((f, label))
    return samples


def main():
    samples = collect_test_images()
    if not samples:
        print(f"[ERROR] test/ 目录下没找到图片！")
        return

    n_species = len(set(l for _, l in samples))
    print(f"\n  测试集: {len(samples)} 张图片, {n_species} 个物种\n")

    model, xgb, le = load_model()
    species_list = list(le.classes_)

    # 检查遗漏物种
    missing = sorted(set(l for _, l in samples) - set(species_list))
    if missing:
        print(f"\n  [WARN] 以下物种不在模型中: {', '.join(missing)}")

    print(f"\n[3/3] 开始预测...")

    results = []
    correct = 0
    per_sp_correct = defaultdict(int)
    per_sp_total = defaultdict(int)
    confusion = defaultdict(lambda: defaultdict(int))

    for i, (img_path, true_label) in enumerate(samples):
        emb = encode(img_path, model).reshape(1, -1)
        probs = xgb.predict_proba(emb)[0]
        top_idx = np.argsort(probs)[::-1]

        top1 = species_list[int(top_idx[0])]
        top1_conf = float(probs[int(top_idx[0])]) * 100
        top2 = species_list[int(top_idx[1])]
        top2_conf = float(probs[int(top_idx[1])]) * 100

        results.append((img_path.name, true_label, top1, top1_conf, top2, top2_conf))
        per_sp_total[true_label] += 1
        confusion[true_label][top1] += 1

        if top1 == true_label:
            correct += 1
            per_sp_correct[true_label] += 1

        # 进度
        if (i + 1) % 50 == 0:
            acc = correct / (i + 1) * 100
            print(f"  [{i+1}/{len(samples)}] running acc: {acc:.1f}% ({correct}/{i+1})")

    # === 总体结果 ===
    acc = correct / len(samples) * 100
    print(f"\n{'='*60}")
    print(f"  测试准确率: {correct}/{len(samples)} = {acc:.1f}%")
    print(f"{'='*60}")

    # Tier 统计
    tier1 = sum(1 for r in results if r[3] >= 85)
    tier2 = sum(1 for r in results if 50 <= r[3] < 85)
    tier3 = sum(1 for r in results if r[3] < 50)
    print(f"\n  Tier 分布: HIGH(≥85%): {tier1} | MED(50-85%): {tier2} | LOW(<50%): {tier3}")

    # Tier 准确率
    for tier_name, lo, hi in [("HIGH ≥85%", 85, 101), ("MED 50-85%", 50, 85), ("LOW <50%", 0, 50)]:
        subset = [(r[1], r[2]) for r in results if lo <= r[3] < hi]
        if subset:
            c = sum(1 for tl, pl in subset if tl == pl)
            print(f"  {tier_name}: {c}/{len(subset)} = {c/len(subset)*100:.1f}%")
        else:
            print(f"  {tier_name}: N/A")

    # 每种菌准确率
    print(f"\n  按物种准确率:")
    print(f"  {'Species':<40s} {'Correct/Total':>12s} {'Acc':>6s}")
    print(f"  {'-'*40} {'-'*12} {'-'*6}")
    for sp in sorted(per_sp_total.keys(), key=lambda s: per_sp_total[s], reverse=True):
        c = per_sp_correct[sp]
        t = per_sp_total[sp]
        a = c / t * 100
        bar = "#" * int(a / 5) + "-" * (20 - int(a / 5))
        print(f"  {sp:<40s} {c:>3d}/{t:<4d}      {a:>5.1f}% [{bar}]")

    # 混淆 Top-10
    errors = [(r[0], r[1], r[2], r[3]) for r in results if r[1] != r[2]]
    if errors:
        cp = defaultdict(int)
        for _, tl, pl, _ in errors:
            cp[(tl, pl)] += 1
        print(f"\n  Top-10 混淆对:")
        for (tsp, psp), cnt in sorted(cp.items(), key=lambda x: -x[1])[:10]:
            print(f"    {tsp} → {psp}: {cnt}x")

        print(f"\n  错误详情 (前20):")
        for name, tsp, psp, conf in errors[:20]:
            print(f"    {name}: {psp} ({conf:.0f}%)  正确={tsp}")
        if len(errors) > 20:
            print(f"    ... 还有 {len(errors)-20} 个错误")

    # 导出 CSV
    csv_path = SCRIPT_DIR / "test_results_tuned.csv"
    import csv
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Image", "TrueLabel", "Prediction", "Confidence", "2ndChoice", "2ndConf", "Correct"])
        for name, tl, pl, conf, p2, conf2 in results:
            w.writerow([name, tl, pl, f"{conf:.1f}%", p2, f"{conf2:.1f}%", "Y" if tl == pl else "N"])
    print(f"\n  CSV 已保存: {csv_path}")


if __name__ == "__main__":
    main()
