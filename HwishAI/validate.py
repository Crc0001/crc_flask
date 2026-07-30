# -*- coding: utf-8 -*-
"""验证脚本 v3: 结果写入 log 文件，避免输出缓冲问题。"""
import argparse, os, sys, json, pickle, time
from pathlib import Path
from collections import defaultdict

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

LOG_FILE = Path(__file__).parent / "validation_log.txt"

def log(msg):
    """同时输出到 stdout 和 log 文件"""
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# 清空旧日志
LOG_FILE.write_text("", encoding="utf-8")

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from xgboost import XGBClassifier

log("imports done, loading model...")

WORK_DIR = Path(__file__).parent
MODEL_DIR = WORK_DIR / "model"
DEFAULT_TEST = WORK_DIR / "待训练"
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
    device = "cuda" if torch.cuda.is_available() else "cpu"
    import open_clip
    log(f"Device: {device}")
    log("Loading BioCLIP...")
    model, _ = open_clip.create_model_from_pretrained("hf-hub:imageomics/bioclip-2", device=device)
    model = model.to(device).eval()
    log("BioCLIP loaded")
    xgb = XGBClassifier()
    xgb.load_model(str(MODEL_DIR / "xgb.json"))
    le = pickle.load(open(MODEL_DIR / "label_encoder.pkl", "rb"))
    log(f"Classifier: {len(le.classes_)} species")
    return model, xgb, le, device


@torch.no_grad()
def encode_batch(image_paths, model, device):
    tensors, valid, labels = [], [], []
    for p in image_paths:
        try:
            img = Image.open(p).convert("RGB")
            tensors.append(PREPROCESS(img).unsqueeze(0))
            valid.append(p)
            labels.append(p.parent.name)
        except Exception as e:
            log(f"SKIP {p.name}: {e}")
    if not tensors:
        return np.array([]).reshape(0, 768), [], []
    batch = torch.cat(tensors, dim=0).to(device)
    features = model.encode_image(batch)
    features = F.normalize(features, dim=-1)
    return features.cpu().numpy(), valid, labels


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=str(DEFAULT_TEST))
    a = p.parse_args()

    if not (MODEL_DIR / "xgb.json").exists():
        log("ERROR: no model found")
        sys.exit(1)

    model, xgb, le, device = load_model()
    species_list = list(le.classes_)

    # 收集测试图片
    test_dir = Path(a.dir)
    samples = []
    for sd in sorted(test_dir.iterdir()):
        if sd.is_dir():
            label = sd.name
            for f in sd.iterdir():
                if f.suffix.lower() in EXT and f.is_file():
                    samples.append((f, label))

    total = len(samples)
    log(f"Test images: {total} from {len(set(s for _,s in samples))} species")

    if total == 0:
        log("ERROR: no images")
        sys.exit(1)

    # Phase 1: 批量编码
    log(f"Phase 1: encoding {total} images (batch=16)...")
    all_embs, all_true = [], []
    BATCH = 16
    done = 0
    all_paths = [sp for sp, _ in samples]
    for i in range(0, len(all_paths), BATCH):
        batch = all_paths[i:i + BATCH]
        embs, valid, lbls = encode_batch(batch, model, device)
        if len(embs) > 0:
            all_embs.append(embs)
            all_true.extend(lbls)
        done += len(batch)
        if done % 48 == 0 or done >= total:
            log(f"  encoded {min(done, total)}/{total}")

    X = np.vstack(all_embs)
    y_true = np.array(all_true)
    log(f"Encoding done: {X.shape[0]} x {X.shape[1]}")

    # Phase 2: 预测
    log("Phase 2: predicting...")
    probs_all = xgb.predict_proba(X)
    top_idx = np.argsort(probs_all, axis=1)[:, ::-1]

    correct = 0
    tier1 = tier2 = tier3 = 0
    per_sp_correct = defaultdict(int)
    per_sp_total = defaultdict(int)
    per_sp_conf = defaultdict(float)
    confusion = defaultdict(lambda: defaultdict(int))
    errors = []

    for idx in range(X.shape[0]):
        tl = y_true[idx]
        pl = species_list[int(top_idx[idx, 0])]
        conf = float(probs_all[idx, int(top_idx[idx, 0])]) * 100

        per_sp_total[tl] += 1
        confusion[tl][pl] += 1
        if pl == tl:
            correct += 1
            per_sp_correct[tl] += 1
            per_sp_conf[tl] += conf

        if conf >= 85: tier1 += 1
        elif conf >= 50: tier2 += 1
        else: tier3 += 1

        if pl != tl:
            top3 = [(species_list[int(top_idx[idx, j])], float(probs_all[idx, int(top_idx[idx, j])]) * 100) for j in range(3)]
            errors.append((all_paths[idx].name, tl, pl, conf, top3))

    # Report
    acc = correct / total * 100
    log("=" * 60)
    log(f"OVERALL ACCURACY (Top-1): {correct}/{total} = {acc:.1f}%")
    log("=" * 60)
    log(f"Tier 1 [>=85%]: {tier1} ({tier1/total*100:.1f}%)")
    log(f"Tier 2 [50-85%]: {tier2} ({tier2/total*100:.1f}%)")
    log(f"Tier 3 [<50%]: {tier3} ({tier3/total*100:.1f}%)")

    tier1_wrong = sum(1 for e in errors if e[3] >= 85)
    if tier1 > 0:
        log(f"Tier 1 internal accuracy: {tier1 - tier1_wrong}/{tier1} = {(1 - tier1_wrong/tier1)*100:.1f}%")

    log("")
    log("Per-species accuracy:")
    for sp in sorted(per_sp_total.keys(), key=lambda s: per_sp_total[s], reverse=True):
        c = per_sp_correct[sp]
        t = per_sp_total[sp]
        a = c / t * 100
        ac = per_sp_conf[sp] / c if c > 0 else 0
        bar = "#" * int(a / 5) + "-" * (20 - int(a / 5))
        log(f"  {sp:<40s} {c:>3d}/{t:<4d} {a:>5.1f}% [{bar}] avg_conf={ac:>5.1f}%")

    if errors:
        log("")
        log(f"Errors ({len(errors)}):")
        confusion_pairs = defaultdict(int)
        for _, tl, pl, _, _ in errors:
            confusion_pairs[(tl, pl)] += 1
        for (tsp, psp), cnt in sorted(confusion_pairs.items(), key=lambda x: -x[1])[:10]:
            log(f"  {tsp} -> {psp}: {cnt}x")

        log("")
        log("Error details:")
        for name, tsp, psp, conf, top3 in errors[:20]:
            log(f"  {name}: pred={psp}({conf:.0f}%), true={tsp}")
            log(f"    top3: {', '.join(f'{s}({c:.0f}%)' for s,c in top3)}")

    # JSON
    result = {
        "total": total, "correct": correct, "accuracy": round(acc, 2),
        "tier1": tier1, "tier2": tier2, "tier3": tier3,
        "per_species": {sp: {"correct": per_sp_correct[sp], "total": per_sp_total[sp]}
                        for sp in sorted(per_sp_total.keys())},
        "errors": len(errors),
    }
    result_path = WORK_DIR / "validation_result.json"
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"\nSaved: {result_path}")
    log("DONE")


if __name__ == "__main__":
    main()
