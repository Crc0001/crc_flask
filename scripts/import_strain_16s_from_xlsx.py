import pandas as pd
from sqlalchemy import create_engine

# 1. 读取 Excel 文件
file_path = r'C:\Users\Administrator\Desktop\16s和TOF鉴定结果信息及比对-2026.xlsx' # 替换为你的文件路径
df = pd.read_excel(file_path)

# 2. 数据清洗与格式转换
# 截取样本名称的前5个字符作为 strain_code
df['strain_code'] = df['样本名称'].astype(str).str[:5]

# 将 DataFrame 的列名修改为与数据库表结构一致
df_to_upload = df[['strain_code', '序列', '16s物种中文名称', '16s物种英文名称']].rename(columns={
    '序列': 'strain_16s',
    '16s物种中文名称': 'strain_name',
    '16s物种英文名称': 'strain_scientific_name'
})

# 3. 写入数据库

engine = create_engine("mysql+pymysql://root:123456@localhost/crc_ai")

# 写入 strain_16s 表
df_to_upload.to_sql('strain_16s', con=engine, if_exists='append', index=False)

print("数据导入完成！")