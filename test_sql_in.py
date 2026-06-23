import pandas as pd
from sqlalchemy import create_engine, text, inspect
from datetime import datetime
import os
import glob

# ── 配置区（改这里）──────────────────────────────
DB_HOST      = "localhost"
DB_PORT      = 3306
DB_USER      = "root"
DB_PASSWORD  = "123456"
DB_NAME      = "crc_ai"

CSV_FOLDER   = r"C:\Users\Administrator\Desktop\5"

# 主键配置（多字段联合主键用列表）
KEY_COLUMNS  = {
    "medium":              "id",
    "strain_taxonomy":     "id",
    "strain":              "id",
    "strain_growth_cycle": "id",
    "strain_morphology":   "id",
    "strain_medium":       ["strain_id", "medium_id"],  # 联合主键
}
DEFAULT_KEY  = "id"

# 导入顺序（父表在前，子表在后，避免外键报错）
TABLE_ORDER = [
    "medium",
    "strain_taxonomy",
    "strain",
    "strain_morphology",
    "strain_growth_cycle",
    "strain_medium",
]

# 全局字段映射
COLUMN_MAP = {
    "colony_shap":  "colony_shape",
    "colony_colo":  "colony_color",
    "colony_opac":  "colony_opacity",
    "colony_text":  "colony_texture",
    "colony_elev":  "colony_elevation",
    "is_recommen":  "is_recommended",
    "culture_tim":  "culture_time",
    'fingerprint': 'fingerprint_image',
}

# 表级字段映射（优先级高于 COLUMN_MAP）
TABLE_COLUMN_MAP = {}

# NOT NULL 字段默认值（字段名: 默认值）
NULL_DEFAULTS = {
    "created_at": lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "updated_at": lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "strain_rank": lambda: "未分类",
    "is_active":   lambda: "1",
    "is_recommended": lambda: "0",
}
# ────────────────────────────────────────────────

DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
engine    = create_engine(DB_URL)
inspector = inspect(engine)

# 按指定顺序 + 未配置的表追加在后面
csv_files_map = {
    os.path.splitext(os.path.basename(f))[0]: f
    for f in glob.glob(os.path.join(CSV_FOLDER, "*.csv"))
}

ordered_tables = TABLE_ORDER + [t for t in csv_files_map if t not in TABLE_ORDER]
csv_files = [(t, csv_files_map[t]) for t in ordered_tables if t in csv_files_map]
total = len(csv_files)

if total == 0:
    print("❌ 没有找到 CSV 文件，请检查路径！")
    exit()

print(f"找到 {total} 个 CSV 文件（按导入顺序）：")
for i, (t, _) in enumerate(csv_files, 1):
    print(f"  {i}. {t}")

print("\n" + "="*50)
print("开始逐表处理，每张表需要你确认后才会写入")
print("="*50 + "\n")

success, skipped, failed = 0, 0, 0

def read_csv_auto(path):
    for enc in ("utf-8", "gbk", "latin1"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            print(f"  📄 编码: {enc}")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码")

for idx, (table_name, csv_path) in enumerate(csv_files, 1):
    key_col = KEY_COLUMNS.get(table_name, DEFAULT_KEY)
    key_cols = key_col if isinstance(key_col, list) else [key_col]
    print(f"[{idx}/{total}] 表: {table_name}  (主键: {key_col})")

    try:
        # 1. 读取 CSV
        df_csv = read_csv_auto(csv_path)

        # 2. 字段映射
        merged_map = {**COLUMN_MAP, **TABLE_COLUMN_MAP.get(table_name, {})}
        renamed = {k: v for k, v in merged_map.items() if k in df_csv.columns}
        if renamed:
            df_csv = df_csv.rename(columns=renamed)
            print(f"  🔄 字段映射: {renamed}")

        # 3. 字段对比
        db_columns  = {col["name"] for col in inspector.get_columns(table_name)}
        csv_columns = set(df_csv.columns)
        only_in_csv = csv_columns - db_columns
        only_in_db  = db_columns  - csv_columns

        if only_in_csv:
            print(f"  ⚠️  CSV 多出的字段（将被丢弃）: {only_in_csv}")
            df_csv = df_csv[[c for c in df_csv.columns if c in db_columns]]
        if only_in_db:
            print(f"  ℹ️  数据库多出的字段（将填 NULL）: {only_in_db}")

        # 4. 检查主键是否存在
        missing_keys = [k for k in key_cols if k not in db_columns]
        if missing_keys:
            print(f"  ❌ 主键字段 {missing_keys} 在数据库中不存在！")
            print(f"     数据库实际字段: {sorted(db_columns)}")
            failed += 1
            continue

        # 5. NOT NULL 字段填默认值
        for col, default_fn in NULL_DEFAULTS.items():
            if col in db_columns and col in df_csv.columns:
                null_count = df_csv[col].isna().sum()
                if null_count > 0:
                    fill_val = default_fn()
                    df_csv[col] = df_csv[col].fillna(fill_val)
                    print(f"  🔧 '{col}' 空值填充为: {fill_val}（共 {null_count} 条）")

        print(f"  CSV 共 {len(df_csv)} 条")

        # 6. 找出新数据（支持联合主键）
        with engine.connect() as conn:
            cols_sql = ", ".join(f"`{k}`" for k in key_cols)
            df_db = pd.read_sql(text(f"SELECT {cols_sql} FROM `{table_name}`"), conn)

        if len(key_cols) == 1:
            existing = set(df_db[key_cols[0]].astype(str))
            df_new = df_csv[~df_csv[key_cols[0]].astype(str).isin(existing)]
        else:
            existing = set(zip(*[df_db[k].astype(str) for k in key_cols]))
            mask = ~pd.Series(
                list(zip(*[df_csv[k].astype(str) for k in key_cols]))
            ).isin(existing)
            df_new = df_csv[mask.values]

        print(f"  数据库已有 {len(df_db)} 条，可追加 {len(df_new)} 条新数据")

        if len(df_new) == 0:
            print("  ⏭  无新数据，自动跳过\n")
            skipped += 1
            continue

        # 7. 预览
        print("\n  预览新数据（前3条）：")
        print(df_new.head(3).to_string(index=False))
        print()

        # 8. 确认
        while True:
            ans = input(f"  ➤ 确认追加 {len(df_new)} 条到 [{table_name}]？(y=写入 / n=跳过 / q=退出) ").strip().lower()
            if ans in ("y", "n", "q"):
                break
            print("  请输入 y、n 或 q")

        if ans == "q":
            print("\n⚠️  用户中断，已退出。")
            break
        elif ans == "n":
            print("  ⏭  已跳过\n")
            skipped += 1
        else:
            df_new.to_sql(table_name, engine, if_exists="append", index=False)
            print(f"  ✅ 成功追加 {len(df_new)} 条！\n")
            success += 1

    except Exception as e:
        print(f"  ❌ 出错: {e}\n")
        failed += 1

print("="*50)
print(f"处理完成：✅ 成功 {success} 张  ⏭ 跳过 {skipped} 张  ❌ 失败 {failed} 张")
print("="*50)