# -*- coding: utf-8 -*-
"""对比 已训练/ 和 待训练/ 中的图片，删除待训练中与已训练重复的图片。
重复判定：MD5 哈希一致（内容级比对，不看文件名）。
"""
import hashlib, os, sys
from pathlib import Path

# 强制 UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8')

WORK = Path(r"C:\Users\17300\.openclaw\workspace\bioclip_xgboost")
TRAINED = WORK / "已训练"
PENDING = WORK / "待训练"

EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def hash_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_hash_map(root):
    m = {}
    for f in sorted(root.rglob("*")):
        if f.suffix.lower() in EXT and f.is_file():
            md5 = hash_file(f)
            m.setdefault(md5, []).append(str(f))
    return m


print("=" * 60)
print("  已训练 vs 待训练 重复图片检测 (MD5)")
print("=" * 60)

print("\n[1/3] 扫描已训练库...")
trained_map = build_hash_map(TRAINED)
print(f"  已训练: {sum(len(v) for v in trained_map.values())} 张, {len(trained_map)} 个唯一哈希")

print("\n[2/3] 扫描待训练库...")
pending_all = []
for f in sorted(PENDING.rglob("*")):
    if f.suffix.lower() in EXT and f.is_file():
        pending_all.append(f)
print(f"  待训练: {len(pending_all)} 张")

print("\n[3/3] 逐张比对...")
to_delete = []
checked = 0
for f in pending_all:
    checked += 1
    md5 = hash_file(f)
    if md5 in trained_map:
        dup_paths = trained_map[md5]
        species = f.parent.name
        dup_species = [Path(p).parent.name for p in dup_paths]
        to_delete.append((f, dup_paths, dup_species))
    if checked % 200 == 0:
        print(f"  已检查 {checked}/{len(pending_all)}...")

print(f"\n{'=' * 60}")
print(f"  检测结果")
print(f"{'=' * 60}")

if not to_delete:
    print("\n  [OK] 待训练中没有与已训练重复的图片。")
else:
    print(f"\n  发现 {len(to_delete)} 张重复图片:\n")
    for i, (f, dup_paths, dup_species) in enumerate(to_delete, 1):
        print(f"  [{i}] 待训练/{f.parent.name}/{f.name}")
        for dp, ds in zip(dup_paths, dup_species):
            print(f"      已训练/{ds}/{Path(dp).name}")
        print()

    print(f"  正在删除 {len(to_delete)} 张重复图片...")
    deleted = 0
    for f, _, _ in to_delete:
        try:
            os.remove(f)
            deleted += 1
        except Exception as e:
            print(f"  删除失败: {f} - {e}")
    print(f"\n  [DONE] 已删除 {deleted} 张重复图片。")
