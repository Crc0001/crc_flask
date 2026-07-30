# -*- coding: utf-8 -*-
"""
IDE 一键运行: 用 待训练/ 测试模型准确率 (文件夹名=正确答案)
直接 F5 即可，无需命令行参数。
"""
import os, sys, json, csv
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
import pickle, open_clip

SCRIPT_DIR = Path(__file__).parent.resolve()
MODEL_DIR = SCRIPT_DIR / "model"
TEST_DIR  = SCRIPT_DIR / "待训练"

PREPROCESS = transforms.Compose([
    transforms.ToTensor(),
    transforms.Resize((224, 224), antialias=True),
    transforms.Normalize(
        mean=(0.48145466, 0.4578275, 0.40821073),
        std=(0.26862954, 0.26130258, 0.27577711),
    ),
])
EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def load_model():
    print("[Loading] BioCLIP...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _ = open_clip.create_model_from_pretrained(
        "hf-hub:imageomics/bioclip-2", device=device)
    model = model.to(device).eval()
    print(f"[OK] Device: {device}")

    xgb = XGBClassifier()
    xgb.load_model(str(MODEL_DIR / "xgb.json"))
    le = pickle.load(open(MODEL_DIR / "label_encoder.pkl", "rb"))
    print(f"[OK] Classifier: {len(le.classes_)} species")
    return model, xgb, le, device


@torch.no_grad()
def encode(img_path, model, device):
    img = Image.open(img_path).convert("RGB")
    tensor = PREPROCESS(img).unsqueeze(0).to(device)
    features = model.encode_image(tensor)
    features = F.normalize(features, dim=-1)
    return features.cpu().numpy().flatten()


# ============================================================
# 主流程
# ============================================================
print("=" * 70)
print("  BioCLIP + XGBoost  模型验证 (Labeled Mode)")
print(f"  测试目录: {TEST_DIR}")
print("=" * 70)

if not TEST_DIR.exists():
    print(f"\n[ERROR] 测试目录不存在: {TEST_DIR}")
    print("  请确认待训练/ 文件夹下有按菌种分组的图片。")
    input("\nPress Enter to exit...")
    sys.exit(1)

if not (MODEL_DIR / "xgb.json").exists():
    print(f"\n[ERROR] 模型文件不存在: {MODEL_DIR / 'xgb.json'}")
    print("  请先运行 train_classifier.py 训练模型。")
    input("\nPress Enter to exit...")
    sys.exit(1)

# 加载模型
model, xgb, le, device = load_model()
species_list = list(le.classes_)

# 收集测试图片 (子目录 = 标签)
labeled = []
subdirs = sorted([d for d in TEST_DIR.iterdir() if d.is_dir()])
for sd in subdirs:
    label = sd.name
    imgs = sorted([f for f in sd.iterdir()
                   if f.suffix.lower() in EXT and f.is_file()])
    for img in imgs:
        labeled.append((img, label))

if not labeled:
    print(f"\n[ERROR] 待训练/ 下未找到任何图片。")
    input("\nPress Enter to exit...")
    sys.exit(1)

n_species = len(set(l for _, l in labeled))
print(f"\n  测试集: {len(labeled)} 张图片, {n_species} 种菌")

missing = sorted(set(l for _, l in labeled) - set(species_list))
if missing:
    print(f"\n  [WARN] {len(missing)} 种菌不在模型中: {', '.join(missing)}")

# ============================================================
# 逐张预测 + 统计
# ============================================================
print(f"\n{'='*70}")
print(f"  正在测试 {len(labeled)} 张图片...")
print(f"{'='*70}\n")

results = []
correct_top1 = 0
correct_top3 = 0
tier1 = tier2 = tier3 = 0
per_sp_correct = defaultdict(int)
per_sp_total = defaultdict(int)
per_sp_conf = defaultdict(float)
errors = []

for idx, (img_path, true_label) in enumerate(labeled):
    try:
        emb = encode(img_path, model, device).reshape(1, -1)
    except Exception as e:
        print(f"  [SKIP] {img_path.name}: {e}")
        continue

    probs = xgb.predict_proba(emb)[0]
    top_idx = np.argsort(probs)[::-1]

    pred = species_list[int(top_idx[0])]
    conf = float(probs[int(top_idx[0])]) * 100
    alt = species_list[int(top_idx[1])]
    alt_conf = float(probs[int(top_idx[1])]) * 100
    top3_labels = [species_list[int(i)] for i in top_idx[:3]]

    results.append((img_path.name, pred, conf, alt, alt_conf, true_label))

    # Tier
    if conf >= 85: tier1 += 1
    elif conf >= 50: tier2 += 1
    else: tier3 += 1

    # Accuracy
    per_sp_total[true_label] += 1
    if pred == true_label:
        correct_top1 += 1
        per_sp_correct[true_label] += 1
        per_sp_conf[true_label] += conf
    if true_label in top3_labels:
        correct_top3 += 1

    if pred != true_label:
        top3_info = [(species_list[int(i)], float(probs[int(i)]) * 100)
                     for i in top_idx[:3]]
        errors.append((img_path.name, true_label, pred, conf, top3_info))

    if (idx + 1) % 20 == 0 or (idx + 1) == len(labeled):
        acc = correct_top1 / (idx + 1) * 100
        print(f"  Progress: {idx+1}/{len(labeled)}  |  running acc: {acc:.1f}% ({correct_top1}/{idx+1})")

# ============================================================
# 结果表格
# ============================================================
print(f"\n{'='*70}")
print(f"  逐张预测结果")
print(f"{'='*70}")
print(f"\n  {'Image':<26s} {'Prediction':<30s} {'Conf':>6s}  {'2nd':<30s} {'Conf':>6s}  Result")
print(f"  {'-'*26} {'-'*30} {'-'*6}  {'-'*30} {'-'*6}  {'-'*17}")

for name, pred, conf, alt, alt_conf, true_lbl in results:
    if conf >= 85: v = "HIGH"
    elif conf >= 50: v = "MED "
    else: v = "LOW "

    ok = pred == true_lbl
    mark = f"{v} OK" if ok else f"{v} WRONG -> {true_lbl}"
    print(f"  {name:<26s} {pred:<30s} {conf:5.1f}%  {alt:<30s} {alt_conf:5.1f}%  {mark}")

# ============================================================
# 汇总报告
# ============================================================
total = len(labeled)
acc_top1 = correct_top1 / total * 100
acc_top3 = correct_top3 / total * 100

print(f"\n{'='*70}")
print(f"  VALIDATION REPORT")
print(f"{'='*70}")

print(f"\n  [1] Overall Accuracy")
print(f"      Top-1: {correct_top1}/{total} = {acc_top1:.1f}%")
print(f"      Top-3: {correct_top3}/{total} = {acc_top3:.1f}%")

print(f"\n  [2] Tier Distribution")
print(f"      Tier 1 (>=85%): {tier1:>4d}  ({tier1/total*100:5.1f}%)  direct report")
print(f"      Tier 2 (50-85%):{tier2:>4d}  ({tier2/total*100:5.1f}%)  manual review")
print(f"      Tier 3 (<50%):  {tier3:>4d}  ({tier3/total*100:5.1f}%)  MALDI-TOF")

# Tier 内准确率
print(f"\n  [3] Tier Internal Accuracy")
for tier_label, lo, hi in [("Tier 1 [>=85%]", 85, 101), ("Tier 2 [50-85%]", 50, 85), ("Tier 3 [<50%]", 0, 50)]:
    mask = [r[2] >= lo and r[2] < hi for r in results]
    n = sum(mask)
    if n > 0:
        c = sum(1 for i, m in enumerate(mask) if m and results[i][1] == results[i][5])
        flag = "SAFE" if (lo >= 85 and c/n >= 0.9) or (lo < 50 and c/n <= 0.2) else "CHECK"
        print(f"      {tier_label}: {c}/{n} = {c/n*100:.1f}%  [{flag}]")
    else:
        print(f"      {tier_label}: N/A")

print(f"\n  [4] Per-Species Accuracy")
print(f"      {'Species':<40s} {'Correct':>8s} {'Acc':>6s}  AvgConf  Bar")
print(f"      {'-'*40} {'-'*8} {'-'*6}  {'-'*7}  {'-'*20}")
sorted_sp = sorted(per_sp_total.keys(), key=lambda s: (-per_sp_total[s], s))
for sp in sorted_sp:
    c = per_sp_correct[sp]
    t = per_sp_total[sp]
    a = c / t * 100
    ac = per_sp_conf[sp] / c if c > 0 else 0
    bar = "#" * int(a / 5) + "-" * (20 - int(a / 5))
    print(f"      {sp:<40s} {c:>3d}/{t:<4d} {a:>5.1f}%  {ac:>5.1f}%  [{bar}]")

if errors:
    print(f"\n  [5] Top-10 Confusion Pairs")
    confusion_pairs = defaultdict(int)
    for _, tl, pl, _, _ in errors:
        confusion_pairs[(tl, pl)] += 1
    for (tsp, psp), cnt in sorted(confusion_pairs.items(), key=lambda x: -x[1])[:10]:
        print(f"      {tsp}  -->  {psp}: {cnt}x")

    print(f"\n  [6] Error Details ({len(errors)} errors)")
    for name, tsp, psp, conf, top3 in errors[:20]:
        top3_str = ", ".join([f"{s}({c:.0f}%)" for s, c in top3])
        print(f"      {name}")
        print(f"        pred={psp}({conf:.0f}%)  true={tsp}")
        print(f"        top3: {top3_str}")
    if len(errors) > 20:
        print(f"      ... +{len(errors) - 20} more")

# ---- 保存结果 ----
result_json = {
    "total": total, "correct_top1": correct_top1, "accuracy": round(acc_top1, 2),
    "tier1": tier1, "tier2": tier2, "tier3": tier3,
    "per_species": {sp: {"correct": per_sp_correct[sp], "total": per_sp_total[sp]}
                    for sp in sorted_sp},
    "n_errors": len(errors),
}
json_path = SCRIPT_DIR / "validation_result.json"
json.dump(result_json, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n  [JSON] Saved: {json_path}")

# ---- CSV ----
csv_path = SCRIPT_DIR / "test_results.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["Image", "Prediction", "Confidence", "2nd_Choice", "2nd_Conf",
                      "Tier", "True_Label", "Correct"])
    for name, pred, conf, alt, alt_conf, true_lbl in results:
        if conf >= 85: v = "HIGH"
        elif conf >= 50: v = "MED"
        else: v = "LOW"
        ok = "Y" if pred == true_lbl else "N"
        writer.writerow([name, pred, f"{conf:.1f}%", alt, f"{alt_conf:.1f}%",
                         v, true_lbl, ok])
print(f"  [CSV] Saved: {csv_path}")

print(f"\n{'='*70}")
print(f"  DONE. Accuracy: {acc_top1:.1f}% ({correct_top1}/{total})")
print(f"{'='*70}")

# IDE 保持窗口
try:
    input("\nPress Enter to close...")
except EOFError:
    pass
