"""
MALDI-TOF 数据批量导入脚本

功能：
1. 读取 Excel 映射表
2. 遍历数据文件夹
3. 解析 TXT 文件
4. 匹配菌种名称
5. 导入到 maldi_reference 表
"""

import os
import sys
import pandas as pd
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.strain import Strain
from app.models.maldi_reference import MaldiReference
from app.services.maldi_matching import parse_maldi_txt_from_bytes


# 配置路径
EXCEL_PATH = r"C:\Users\Administrator\Desktop\标红TOF数据\微生物项目（455种）工作进度表.xlsx"
DATA_DIR = r"C:\Users\Administrator\Desktop\标红TOF数据"


def read_mapping_table():
    """读取 Excel 映射表"""
    print("正在读取映射表...")
    df = pd.read_excel(EXCEL_PATH)

    # 过滤掉无效数据
    df = df[df['菌种名称（TOF结果）'].notna()]
    df = df[~df['菌种名称（TOF结果）'].str.contains('不长菌|没送检', na=False)]

    print(f"有效数据: {len(df)} 条")
    return df


def find_txt_file(folder_path):
    """在文件夹中查找 TXT 文件"""
    folder = Path(folder_path)
    if not folder.exists():
        return None

    txt_files = list(folder.glob("*.txt"))
    if txt_files:
        return txt_files[0]
    return None


def extract_strain_name(tof_result):
    """
    从 TOF 结果中提取菌种名称

    例如: "蜡样芽孢杆菌  Bacillus cereus" -> "蜡样芽孢杆菌"
    """
    if not tof_result or pd.isna(tof_result):
        return None

    tof_str = str(tof_result).strip()

    # 去除括号内的内容
    import re
    tof_str = re.sub(r'[（(].*?[）)]', '', tof_str).strip()

    # 分割中英文，取中文部分
    parts = tof_str.split()
    if parts:
        chinese_part = parts[0].strip()
        return chinese_part
    return None


def find_strain_in_db(strain_name):
    """在数据库中查找菌种"""
    if not strain_name:
        return None

    # 尝试精确匹配
    strain = Strain.query.filter_by(name=strain_name).first()
    if strain:
        return strain

    # 尝试模糊匹配
    strain = Strain.query.filter(Strain.name.like(f'%{strain_name}%')).first()
    if strain:
        return strain

    # 尝试科学名匹配
    strain = Strain.query.filter(Strain.scientific_name.like(f'%{strain_name}%')).first()
    return strain


def import_data():
    """批量导入数据"""
    # 设置控制台编码
    import sys
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

    app = create_app()

    with app.app_context():
        # 读取映射表
        df = read_mapping_table()

        success_count = 0
        skip_count = 0
        error_count = 0
        not_found_strains = []

        print("\n开始导入数据...\n")

        for idx, row in df.iterrows():
            glycerol_code = row['甘油菌编号']
            tof_result = row['菌种名称（TOF结果）']

            print(f"[{idx+1}/{len(df)}] 处理 {glycerol_code}: {tof_result}")

            # 提取菌种名称
            strain_name = extract_strain_name(tof_result)
            if not strain_name:
                print(f"  ✗ 无法提取菌种名称")
                skip_count += 1
                continue

            # 查找数据文件夹
            folder_path = os.path.join(DATA_DIR, glycerol_code)
            if not os.path.exists(folder_path):
                print(f"  ✗ 文件夹不存在: {folder_path}")
                skip_count += 1
                continue

            # 查找 TXT 文件
            txt_file = find_txt_file(folder_path)
            if not txt_file:
                print(f"  ✗ 未找到 TXT 文件")
                skip_count += 1
                continue

            # 在数据库中查找菌种
            strain = find_strain_in_db(strain_name)
            if not strain:
                print(f"  ✗ 数据库中未找到菌种: {strain_name}")
                not_found_strains.append(strain_name)
                skip_count += 1
                continue

            print(f"  ✓ 匹配到菌种: {strain.name} (ID: {strain.id})")

            # 读取并解析 TXT 文件
            try:
                with open(txt_file, 'rb') as f:
                    file_bytes = f.read()

                parsed_data = parse_maldi_txt_from_bytes(file_bytes)

                if not parsed_data['peaks']:
                    print(f"  ✗ TXT 文件无有效峰数据")
                    skip_count += 1
                    continue

                # 检查是否已存在
                existing = MaldiReference.query.filter_by(
                    strain_id=strain.id,
                    sample_id=glycerol_code
                ).first()

                if existing:
                    print(f"  ⚠ 已存在，跳过")
                    skip_count += 1
                    continue

                # 创建新记录
                maldi_ref = MaldiReference(
                    strain_id=strain.id,
                    sample_id=glycerol_code,
                    peaks=parsed_data['peaks'],
                    peak_count=parsed_data['peak_count']
                )

                db.session.add(maldi_ref)
                db.session.commit()

                print(f"  ✓ 导入成功 ({parsed_data['peak_count']} 个峰)")
                success_count += 1

            except Exception as e:
                print(f"  ✗ 导入失败: {str(e)}")
                error_count += 1
                db.session.rollback()

        # 统计报告
        print("\n" + "="*60)
        print("导入完成！")
        print("="*60)
        print(f"成功: {success_count}")
        print(f"跳过: {skip_count}")
        print(f"失败: {error_count}")
        print(f"总计: {len(df)}")

        if not_found_strains:
            print(f"\n未找到的菌种 ({len(set(not_found_strains))} 种):")
            for strain_name in sorted(set(not_found_strains)):
                print(f"  - {strain_name}")


if __name__ == '__main__':
    import_data()
