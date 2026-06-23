import pymysql


# 1. 复用字节流读取函数（替换成你的字节流来源，比如图片/文件）
def get_binary_bytes(file_path):
    """
    读取文件生成二进制字节流（可替换为你的字节流来源）
    :param file_path: 待读取的文件路径
    :return: bytes类型的字节流，失败返回None
    """
    try:
        with open(file_path, 'rb') as f:
            binary_data = f.read()  # 核心：获取纯bytes类型
        print(f"成功读取文件，字节流长度：{len(binary_data)} 字节")
        return binary_data
    except FileNotFoundError:
        print(f"错误：文件 '{file_path}' 不存在")
        return None
    except Exception as e:
        print(f"读取文件失败：{str(e)}")
        return None


# 2. 数据库配置（你提供的信息）
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'crc_ai',
    'charset': 'utf8mb4'
}


# 3. 核心函数：根据id将字节流写入sample表的mass_spectrum字段
def write_bytes_to_db_by_id(target_id, binary_data):
    """
    根据id更新sample表的mass_spectrum字段（写入字节流）
    :param target_id: 要更新的记录id（整数）
    :param binary_data: 要写入的bytes类型字节流
    :return: 布尔值，更新成功返回True，失败返回False
    """
    # 校验参数：确保binary_data是bytes类型
    if not isinstance(binary_data, bytes):
        print("错误：传入的不是bytes类型的字节流！")
        return False

    conn = None
    try:
        # 建立数据库连接
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()

        # 先检查指定id是否存在（避免更新空记录）
        check_sql = "SELECT id FROM sample WHERE id = %s"
        cursor.execute(check_sql, (target_id,))
        if not cursor.fetchone():
            print(f"错误：id={target_id} 的记录不存在！")
            return False

        # 核心：参数化更新语句（按id写入字节流）
        update_sql = """
        UPDATE sample 
        SET mass_spectrum = %s 
        WHERE id = %s
        """
        # 参数顺序：字节流在前，id在后，严格对应SQL中的%s占位符
        affected_rows = cursor.execute(update_sql, (binary_data, target_id))

        conn.commit()

        if affected_rows > 0:
            print(f"成功！id={target_id} 的mass_spectrum字段已写入字节流")

            # 可选：读取验证（确认写入的字节流正确）
            cursor.execute("SELECT mass_spectrum FROM sample WHERE id = %s", (target_id,))
            result = cursor.fetchone()
            if result:
                saved_bytes = result[0]
                print(f"验证：写入的字节流长度 {len(saved_bytes)} 字节（与原数据一致则正确）")
            return True
        else:
            print(f"警告：id={target_id} 的记录未更新（可能无变更）")
            return True

    except pymysql.MySQLError as e:
        print(f"数据库错误：{e}")
        if conn:
            conn.rollback()  # 出错回滚
        return False
    except Exception as e:
        print(f"未知错误：{e}")
        if conn:
            conn.rollback()
        return False
    finally:
        # 关闭连接（无论成功/失败都要执行）
        if conn:
            cursor.close()
            conn.close()


# -------------- 测试调用 --------------
if __name__ == "__main__":
    # 替换为你的实际参数：目标id + 字节流来源文件路径

    target_id = 19 #写入的记录id
    file_path = r"C:\Users\Administrator\Desktop\菌种库网页版数据-20260131\嗜麦芽寡养单胞菌  Stenotrophomonas maltophilia HS086\19.PNG"  # 你的字节流来源文件（图片/其他二进制文件）

    # 1. 获取字节流
    binary_data = get_binary_bytes(file_path)

    # 2. 按id写入数据库
    if binary_data:
        write_bytes_to_db_by_id(target_id, binary_data)