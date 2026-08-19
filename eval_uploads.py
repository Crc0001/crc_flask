"""对 app/static/uploads 中 HS 菌种原始皿图做识别评测。

用 strain 数据库把 HS 编号映射为拉丁名，再映射到分类器 44 类；
每个映射上的菌种取其文件夹下（含 day 子目录）最多 10 张图，
跑生产同款管线（培养皿裁剪 -> 切片选块聚合 -> 整皿覆盖），统计命中。
"""

import json
import os
import random

import pymysql

import eval_strain_recognition as E
from app.services.yolo_service import classify_images  # noqa: F401  保持导入链一致

UPLOAD_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "static", "uploads")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_results")
SEED = 42
MAX_PER_STRAIN = 10

# 数据库名 -> 分类器类别名 的别名修正（同物异名/改名）
ALIASES = {
    "Staphylococcus ureilyticus": "Staphylococcus ureilyticu",
    "Moraxella osloensis": "Faucicola osloensis",
    "Escherichia vulneris": "Pseudescherichia vulneris",
    "Bacillus megaterium": "Priestia megaterium",
}

CLASSIFIER_CLASSES = {
    "Acinetobacter oryzae", "Acinetobacter seifertii", "Arthrobacter gandavensis",
    "Aureobasidium melanogenum", "Bacillus aerius", "Bacillus cabrialesii",
    "Bacillus cereus", "Bacillus haynesii", "Bacillus infantis",
    "Bacillus manliponensis", "Bacillus piscis", "Bacillus pumilus",
    "Bacillus subtilis", "Bacillus thuringiensis", "Brachybacterium conglomeratum",
    "Brachybacterium paraconglomeratum", "Brevibacillus agri", "Brevundimonas huaxiensis",
    "Burkholderia arboris", "Chryseobacterium hagamense", "Chryseobacterium indologenes",
    "Chryseobacterium mulctrae", "Enterobacter quasihormaechei", "Enterococcus innesii",
    "Faucicola osloensis", "Kocuria rhizophila", "Methylorubrum populi",
    "Micrococcus yunnanensis", "Pantoea ananatis", "Priestia megaterium",
    "Pseudescherichia vulneris", "Pseudomonas parafulva", "Ralstonia pickettii",
    "Serratia marcescens", "Sphingomonas leidyi", "Staphylococcus capitis",
    "Staphylococcus cohnii", "Staphylococcus epidermidis", "Staphylococcus petrasii",
    "Staphylococcus roterodami", "Staphylococcus taiwanensis", "Staphylococcus ureilyticu",
    "Stenotrophomonas maltophilia", "Stenotrophomonas pavanii",
}


def get_upload_folders():
    folders = []
    for name in sorted(os.listdir(UPLOAD_ROOT)):
        path = os.path.join(UPLOAD_ROOT, name)
        if os.path.isdir(path):
            folders.append(name)
    return folders


def get_db_mapping():
    conn = pymysql.connect(
        host="localhost", user="root", password="123456",
        database="crc_ai", charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT strain_code, scientific_name FROM strain "
                "WHERE strain_code IS NOT NULL"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    mapping = {}
    for code, sci in rows:
        code = (code or "").strip()
        sci = (sci or "").strip()
        if code:
            mapping[code] = sci
    return mapping


def main():
    folders = get_upload_folders()
    db_map = get_db_mapping()
    mapped = {}
    skipped = {}
    for folder in folders:
        code = folder.strip()
        sci = db_map.get(code)
        if not sci:
            skipped[folder] = "数据库无该编号"
            continue
        cls = ALIASES.get(sci, sci)
        if E.norm_name(cls) in {E.norm_name(c) for c in CLASSIFIER_CLASSES}:
            mapped[folder] = cls
        else:
            skipped[folder] = sci
    print(f"uploads 目录: {len(folders)} 个; 映射到模型44类: {len(mapped)} 个; 跳过: {len(skipped)} 个", flush=True)
    for k, v in skipped.items():
        print(f"  跳过 {k}: {v}", flush=True)

    rng = random.Random(SEED)
    details = []
    for folder, true_name in sorted(mapped.items()):
        folder_path = os.path.join(UPLOAD_ROOT, folder)
        files = E.list_image_files(folder_path)
        if not files:
            print(f"[{folder}] {true_name}: 无图片", flush=True)
            continue
        sample = rng.sample(files, min(MAX_PER_STRAIN, len(files)))
        hits = 0
        for f in sample:
            try:
                image = E.read_bgr(f)
                clf, pc, sel, _ = E.process_image(image)
                top1 = clf["top3"][0]["species_name"] if clf and clf.get("top3") else ""
                top3 = [i["species_name"] for i in clf["top3"]] if clf and clf.get("top3") else []
                conf = clf["top3"][0]["confidence"] if clf and clf.get("top3") else 0.0
                ok1 = E.norm_name(top1) == E.norm_name(true_name)
                ok3 = any(E.norm_name(t) == E.norm_name(true_name) for t in top3)
            except Exception as exc:
                top1, top3, conf, ok1, ok3, pc, sel = "", [], 0.0, False, False, {"error": str(exc)}, {}
            hits += int(ok1)
            details.append({
                "folder": folder, "true_name": true_name, "file": f,
                "pred_top1": top1, "pred_top3": top3, "conf": conf,
                "correct_top1": ok1, "correct_top3": ok3,
                "plate_applied": pc.get("applied", False),
                "aggregated": sel.get("aggregated", False),
                "aggregated_tiles": sel.get("aggregated_tiles", 0),
            })
        print(f"[{folder}] {true_name}: {hits}/{len(sample)} 命中, {len(sample)} 张", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "uploads_eval_details.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(details, fh, ensure_ascii=False, indent=2)

    # 按类汇总
    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "h1": 0, "h3": 0})
    for d in details:
        agg[d["true_name"]]["n"] += 1
        agg[d["true_name"]]["h1"] += int(d["correct_top1"])
        agg[d["true_name"]]["h3"] += int(d["correct_top3"])
    print("\n=== 分菌种汇总 ===", flush=True)
    for name, s in sorted(agg.items(), key=lambda kv: -(kv[1]["h1"] / kv[1]["n"])):
        print(f"{name}: Top1 {s['h1']}/{s['n']}={s['h1']/s['n']:.0%}  Top3 {s['h3']}/{s['n']}={s['h3']/s['n']:.0%}", flush=True)
    total = len(details)
    h1 = sum(d["correct_top1"] for d in details)
    h3 = sum(d["correct_top3"] for d in details)
    print(f"总计: {h1}/{total}={h1/total:.0%} Top1, {h3}/{total}={h3/total:.0%} Top3", flush=True)
    print(f"结果文件: {out_path}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
