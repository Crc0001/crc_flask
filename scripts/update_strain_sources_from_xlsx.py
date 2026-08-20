"""
通过 XLSX 覆盖更新菌种来源（strain_source）

逻辑：
1. 从 Excel 读取「编号(如HS014)」和「来源」
2. 用编号匹配 maldi_reference.sample_id
3. 找到对应 strain_id 后，覆盖该菌种在 strain_source 的来源记录

默认是 dry-run（只预览，不落库）
落库请加 --apply

用法示例：
python update_strain_sources_from_xlsx.py --xlsx "C:/path/to/your.xlsx" --apply

可选参数：
--code-col   编号列名，默认自动识别（编号/甘油菌编号/菌株编号/HS编号/sample_id）
--source-col 来源列名，默认自动识别（来源/采样来源/来源位置/source）
"""

import argparse
import os
import re
import sys
from collections import defaultdict

import pandas as pd

# 脚本位于 scripts/：把仓库根目录加入 sys.path，保证可 import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models.maldi_reference import MaldiReference
from app.models.strain import StrainSource, Strain


DEFAULT_XLSX = r"C:\Users\Administrator\Desktop\系统中菌种来源(1).xlsx"

CODE_CANDIDATES = ["编号"]
SOURCE_CANDIDATES = ["来源"]


def normalize_code(raw: str) -> str:
    """把各种写法统一成 HS### 形式，如 hs14 -> HS014。"""
    if raw is None:
        return ""
    s = str(raw).strip().upper()
    if not s:
        return ""

    # 提取 HS + 数字
    m = re.search(r"HS\s*0*(\d+)", s)
    if m:
        return f"HS{int(m.group(1)):03d}"

    # 如果只有数字，也按 HS### 处理
    if s.isdigit():
        return f"HS{int(s):03d}"

    # 其他情况原样返回（例如本来就不是HS体系）
    return s


def pick_column(columns, explicit_name, candidates, label):
    if explicit_name:
        if explicit_name not in columns:
            raise ValueError(f"指定的{label}列不存在: {explicit_name}")
        return explicit_name

    for c in candidates:
        if c in columns:
            return c

    raise ValueError(
        f"未找到{label}列。当前列: {list(columns)}；可用候选: {candidates}"
    )


def main():
    parser = argparse.ArgumentParser(description="覆盖更新菌种来源")
    parser.add_argument("--xlsx", default=DEFAULT_XLSX, help="xlsx 文件路径")
    parser.add_argument("--code-col", default=None, help="编号列名")
    parser.add_argument("--source-col", default=None, help="来源列名")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库（默认仅预览）")
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        print(f"读取文件: {args.xlsx}")
        df = pd.read_excel(args.xlsx)
        print(f"总行数: {len(df)}")

        code_col = pick_column(df.columns, args.code_col, CODE_CANDIDATES, "编号")
        source_col = pick_column(df.columns, args.source_col, SOURCE_CANDIDATES, "来源")
        print(f"使用列 -> 编号: {code_col} | 来源: {source_col}")

        # 预处理：从 Excel 汇总为 code -> {source1, source2...}
        code_to_sources = defaultdict(set)
        invalid_rows = 0

        for _, row in df.iterrows():
            code_raw = row.get(code_col)
            source_raw = row.get(source_col)

            code = normalize_code(code_raw)
            source = "" if pd.isna(source_raw) else str(source_raw).strip()

            if not code or not source:
                invalid_rows += 1
                continue

            code_to_sources[code].add(source)

        print(f"有效编号数: {len(code_to_sources)}，无效行: {invalid_rows}")

        # 建立 code -> strain_id 映射
        # 1) 优先用 maldi_reference.sample_id（已有TOF谱的映射）
        # 2) 再回退到 strain.strain_code（覆盖全库菌种）
        code_to_strain = {}
        maldi_mapped = 0
        strain_code_mapped = 0

        refs = MaldiReference.query.all()
        for ref in refs:
            if not ref.sample_id:
                continue
            ncode = normalize_code(ref.sample_id)
            if ncode and ncode not in code_to_strain:
                code_to_strain[ncode] = ref.strain_id
                maldi_mapped += 1

        strains = Strain.query.all()
        for s in strains:
            if not s.strain_code:
                continue
            ncode = normalize_code(s.strain_code)
            if ncode and ncode not in code_to_strain:
                code_to_strain[ncode] = s.id
                strain_code_mapped += 1

        print(f"映射来源统计: maldi_reference={maldi_mapped}, strain.strain_code={strain_code_mapped}")

        # 汇总要覆盖的数据：strain_id -> set(sources)
        strain_to_sources = defaultdict(set)
        not_found_codes = []

        for code, sources in code_to_sources.items():
            strain_id = code_to_strain.get(code)
            if not strain_id:
                not_found_codes.append(code)
                continue
            for s in sources:
                strain_to_sources[strain_id].add(s)

        print(f"可匹配到 strain 的编号数: {len(code_to_sources) - len(not_found_codes)}")
        print(f"未匹配编号数: {len(not_found_codes)}")
        if not_found_codes:
            print("未匹配编号(前20个):", not_found_codes[:20])

        # 预览覆盖计划
        total_delete = 0
        total_insert = 0
        preview_lines = []

        for strain_id, new_sources in strain_to_sources.items():
            old_count = StrainSource.query.filter_by(strain_id=strain_id).count()
            total_delete += old_count
            total_insert += len(new_sources)
            preview_lines.append((strain_id, old_count, len(new_sources), sorted(new_sources)))

        print("\n==== 覆盖预览 ====")
        print(f"涉及菌种数: {len(preview_lines)}")
        print(f"将删除旧来源记录: {total_delete}")
        print(f"将新增来源记录: {total_insert}")

        for strain_id, old_count, new_count, srcs in preview_lines[:20]:
            print(f"strain_id={strain_id}: 旧{old_count}条 -> 新{new_count}条 | {srcs}")

        if not args.apply:
            print("\n当前为 dry-run，未写入数据库。")
            print("确认无误后执行: --apply")
            return

        # 实际覆盖
        try:
            for strain_id, _, _, srcs in preview_lines:
                StrainSource.query.filter_by(strain_id=strain_id).delete()
                for src in srcs:
                    db.session.add(StrainSource(strain_id=strain_id, location=src))

            db.session.commit()
            print("\n✅ 覆盖更新完成")
            print(f"已覆盖菌种数: {len(preview_lines)}")
            print(f"删除旧记录: {total_delete}")
            print(f"新增记录: {total_insert}")

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 更新失败，已回滚: {e}")
            raise


if __name__ == "__main__":
    main()
