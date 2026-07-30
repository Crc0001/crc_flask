# -*- coding: utf-8 -*-
"""快速预测 test/ 文件夹中所有图片 (使用 model_tuned 46种菌模型)"""
import os, sys
from pathlib import Path
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import numpy as np
import torch, torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from xgboost import XGBClassifier
import pickle, open_clip

BASE = Path(__file__).parent
TEST_DIR = BASE / "test"
MODEL_DIR = BASE / "model_tuned"
EXT = {".jpg", ".jpeg", ".png", ".bmp"}

PREPROCESS = transforms.Compose([
    transforms.ToTensor(),
    transforms.Resize((224, 224), antialias=True),
    transforms.Normalize(mean=(0.48145466,0.4578275,0.40821073), std=(0.26862954,0.26130258,0.27577711)),
])

print("=" * 70)
print("  BioCLIP + XGBoost 快速预测 (model_tuned / 46种菌)")
print("=" * 70)

# 加载模型
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\n[1/3] 加载 BioCLIP ... ({device})")
model, _ = open_clip.create_model_from_pretrained("hf-hub:imageomics/bioclip-2", device=device)
model = model.to(device).eval()

print(f"[2/3] 加载 XGBoost (model_tuned) ...")
xgb = XGBClassifier()
xgb.load_model(str(MODEL_DIR / "xgb.json"))
le = pickle.load(open(MODEL_DIR / "label_encoder.pkl", "rb"))
print(f"       物种数: {len(le.classes_)}")

# 收集图片
imgs = sorted([f for f in TEST_DIR.iterdir() if f.suffix.lower() in EXT and f.is_file()])
if not imgs:
    sub_imgs = []
    for d in sorted(TEST_DIR.iterdir()):
        if d.is_dir():
            sub_imgs.extend(sorted([f for f in d.iterdir() if f.suffix.lower() in EXT and f.is_file()]))
    imgs = sub_imgs
if not imgs:
    print(f"\n[ERROR] test/ 中没有图片文件")
    sys.exit(1)
print(f"\n[3/3] 预测 {len(imgs)} 张图片 ...\n")

# 预测
species_list = list(le.classes_)
results = []
for i, img_path in enumerate(imgs):
    img = Image.open(img_path).convert("RGB")
    tensor = PREPROCESS(img).unsqueeze(0).to(device)
    with torch.no_grad():
        emb = model.encode_image(tensor)
        emb = F.normalize(emb, dim=-1).cpu().numpy()
    probs = xgb.predict_proba(emb)[0]
    top3 = np.argsort(probs)[::-1][:3]
    results.append((img_path.name, species_list[top3[0]], probs[top3[0]] * 100))

# 输出
print(f"  {'图片':<35s} {'预测结果':<30s} {'置信度':>8s}   判定")
print(f"  {'-'*35} {'-'*30} {'-'*8}    {'-'*12}")
for name, pred, conf in results:
    if conf >= 85: v = "HIGH 直接报告"
    elif conf >= 50: v = "MED  人工复核"
    else: v = "LOW  MALDI-TOF"
    print(f"  {name:<35s} {pred:<30s} {conf:>6.1f}%   {v}")

print(f"\n  完成。HIGH: {sum(1 for r in results if r[2]>=85)} | MED: {sum(1 for r in results if 50<=r[2]<85)} | LOW: {sum(1 for r in results if r[2]<50)}")
