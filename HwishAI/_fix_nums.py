import re
path = r'C:\Users\17300\Desktop\bioclip_xgboost\build_meiyu_ppt.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix directory
content = content.replace('21株菌落形态实拍（分三页）', '21株菌落形态实拍（分四页）')

# Fix slide numbers for shifted analysis+closing slides
replacements = [
    ('梅雨特征分析（一）", "芽孢杆菌检出特征 & 葡萄球菌优势分布", 12,',
     '梅雨特征分析（一）", "芽孢杆菌检出特征 & 葡萄球菌优势分布", 13,'),
    ('梅雨特征分析（二）", "放线菌分布 & 特殊环境菌种", 13,',
     '梅雨特征分析（二）", "放线菌分布 & 特殊环境菌种", 14,'),
    ('整体分析与风险提示", "菌群组成 · 培养基效果 · 16S可信度 · 风险矩阵", 14,',
     '整体分析与风险提示", "菌群组成 · 培养基效果 · 16S可信度 · 风险矩阵", 15,'),
    ('结论与建议", "梅雨季环境微生物管控行动指南", 15,',
     '结论与建议", "梅雨季环境微生物管控行动指南", 16,'),
]
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f'Replaced: {old[:50]}...')
    else:
        print(f'NOT FOUND: {old[:50]}...')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done.')
