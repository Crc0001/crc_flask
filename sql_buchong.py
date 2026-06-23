# import pandas as pd
# from sqlalchemy import create_engine, text
#
# DB_URL   = "mysql+pymysql://root:123456@localhost/crc_ai?charset=utf8mb4"
# CSV_PATH = r"C:\Users\Administrator\Desktop\5\strain.csv"
#
# engine = create_engine(DB_URL)
#
# # 读取 CSV
# df = pd.read_csv(CSV_PATH, dtype=str, encoding="gbk")  # 自动换 utf-8
#
# # 字段映射
# df = df.rename(columns={"fingerprint": "fingerprint_image"})
#
# # 只取 id 和 fingerprint_image 两列，且不为空的行
# df_fix = df[["id", "fingerprint_image"]].dropna(subset=["fingerprint_image"])
# print(f"需要更新 {len(df_fix)} 条记录")
#
# # 逐条 UPDATE
# with engine.begin() as conn:
#     for _, row in df_fix.iterrows():
#         conn.execute(
#             text("UPDATE strain SET fingerprint_image = :val WHERE id = :id"),
#             {"val": row["fingerprint_image"], "id": row["id"]}
#         )
#
# print("✅ 更新完成！")
