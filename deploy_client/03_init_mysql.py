# -*- coding: utf-8 -*-
"""03 - 初始化客户空库：建库、建应用账号、导入空表结构（零业务数据）。

前置：客户机器已装 MySQL 8（root 密码已知）。本脚本用 MySQL 自带 mysql.exe 执行。
用法：C:\\HwishAI\\venv\\Scripts\\python.exe 03_init_mysql.py
"""
import getpass
import os
import subprocess
import sys
from pathlib import Path

DB_NAME = "crc_ai"
APP_USER = "hwishai_app"
SCHEMA_FILE = Path(__file__).resolve().parent / "init_empty_db.sql"


def find_mysql():
    candidates = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
        r"C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin\mysql.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # PATH 里找
    import shutil
    found = shutil.which("mysql")
    return found


def run_mysql(mysql, database, stdin_bytes):
    env = dict(os.environ)
    env["MYSQL_PWD"] = root_password
    proc = subprocess.run(
        [mysql, "-uroot", "--default-character-set=utf8mb4", database],
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if proc.returncode != 0:
        print("[ERROR] mysql 执行失败：")
        print(proc.stderr.decode("utf-8", errors="replace"))
        sys.exit(1)


def main():
    global root_password

    mysql = find_mysql()
    if not mysql:
        print("[ERROR] 未找到 mysql.exe，请先安装 MySQL 8（Server 组件）并确保 root 可登录。")
        input("按回车退出...")
        sys.exit(1)
    print("使用 mysql.exe:", mysql)

    root_password = getpass.getpass("请输入 MySQL root 密码: ")

    app_password = getpass.getpass("为应用设置数据库密码（建议字母数字组合）: ")
    app_password2 = getpass.getpass("再次输入确认: ")
    if not app_password or app_password != app_password2:
        print("[ERROR] 两次输入的密码不一致。")
        sys.exit(1)
    if any(ch in app_password for ch in ("'", '"', "\\", ";")):
        print("[ERROR] 密码不能包含引号、反斜杠或分号。")
        sys.exit(1)

    setup_sql = (
        f"CREATE DATABASE IF NOT EXISTS {DB_NAME} "
        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        f"CREATE USER IF NOT EXISTS '{APP_USER}'@'localhost' IDENTIFIED BY '{app_password}';\n"
        f"CREATE USER IF NOT EXISTS '{APP_USER}'@'127.0.0.1' IDENTIFIED BY '{app_password}';\n"
        # 最小权限：业务读写 + 表结构维护；不给 GRANT/FILE/SUPER 等管理权限
        f"GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,DROP,REFERENCES "
        f"ON {DB_NAME}.* TO '{APP_USER}'@'localhost';\n"
        f"GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,DROP,REFERENCES "
        f"ON {DB_NAME}.* TO '{APP_USER}'@'127.0.0.1';\n"
        f"FLUSH PRIVILEGES;\n"
    )
    print("创建数据库与账号 ...")
    run_mysql(mysql, "", setup_sql.encode("utf-8"))

    if not SCHEMA_FILE.exists():
        print("[ERROR] 缺少 init_empty_db.sql")
        sys.exit(1)
    print("导入空表结构（零数据）...")
    run_mysql(mysql, DB_NAME, SCHEMA_FILE.read_bytes())

    print("")
    print(f"[完成] 数据库 {DB_NAME} 已就绪：应用账号 {APP_USER}，业务表已建（无任何数据）。")
    print("请把上面设置的【应用数据库密码】填到 04_configure.py 里。")
    input("按回车退出...")


if __name__ == "__main__":
    main()
