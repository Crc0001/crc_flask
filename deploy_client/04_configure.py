# -*- coding: utf-8 -*-
"""04 - 交互式生成本机配置 instance\\config.py。

用法：C:\\HwishAI\\venv\\Scripts\\python.exe 04_configure.py
生成位置：C:\\HwishAI\\instance\\config.py（自动生成随机 SECRET_KEY）。
"""
import getpass
import secrets
import sys
from pathlib import Path
from urllib.parse import quote_plus

INSTALL_ROOT = Path(r"C:\HwishAI")
INSTANCE_DIR = INSTALL_ROOT / "instance"


def ask(text, default=""):
    value = input(f"{text}" + (f"（回车默认 {default}）" if default else "") + ": ").strip()
    return value or default


def ask_password(text):
    p1 = getpass.getpass(f"{text}: ")
    p2 = getpass.getpass("再次确认: ")
    if not p1 or p1 != p2:
        print("[ERROR] 两次输入不一致或为空，请重试。")
        sys.exit(1)
    return p1


def main():
    print("=" * 60)
    print("HwishAI 菌种识别系统 · 客户端配置向导（生产配置）")
    print("=" * 60)

    api_base = ask("我方识别/知识库服务地址（如 https://api.xxxx.com）")
    if not api_base.startswith(("http://", "https://")):
        print("[ERROR] 服务地址必须以 http:// 或 https:// 开头。")
        sys.exit(1)
    machine_token = ask("客户机器令牌（我方 VENDOR_API_TOKENS 白名单内）")
    if not machine_token:
        print("[ERROR] 机器令牌不能为空。")
        sys.exit(1)

    db_user = ask("数据库应用账号", "hwishai_app")
    db_password = getpass.getpass("数据库应用账号密码: ")
    if not db_password:
        print("[ERROR] 数据库密码不能为空。")
        sys.exit(1)

    admin_username = ask("客户管理员登录账号", "admin")
    admin_password = ask_password("客户管理员初始密码（至少8位，客户首次登录需改密）")
    if len(admin_password) < 8:
        print("[ERROR] 密码至少 8 位。")
        sys.exit(1)

    super_password = ask_password("厂家超级管理员 hwishai 的密码（我方运维用）")
    if len(super_password) < 8:
        print("[ERROR] 密码至少 8 位。")
        sys.exit(1)

    secret_key = secrets.token_hex(32)

    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    content = f'''# -*- coding: utf-8 -*-
# 本文件由部署配置向导生成（04_configure.py），请勿手工随意修改。
SECRET_KEY = "{secret_key}"

# 我方模型/知识库服务
HWISHAI_API_BASE_URL = "{api_base.rstrip('/')}"
HWISHAI_API_TOKEN = "{machine_token}"

# 本地业务库（全新空库）
SQLALCHEMY_DATABASE_URI = "mysql+pymysql://{db_user}:{quote_plus(db_password)}@localhost/crc_ai"

# 首次启动自动创建的账号
BOOTSTRAP_SUPERADMIN_USERNAME = "hwishai"
BOOTSTRAP_SUPERADMIN_PASSWORD = "{super_password}"
BOOTSTRAP_ADMIN_USERNAME = "{admin_username}"
BOOTSTRAP_ADMIN_PASSWORD = "{admin_password}"
'''
    (INSTANCE_DIR / "config.py").write_text(content, encoding="utf-8")
    print("")
    print(f"[完成] 配置已写入 {INSTANCE_DIR / 'config.py'}")
    print("下一步：运行 05_install_service.bat 注册开机自启服务。")
    input("按回车退出...")


if __name__ == "__main__":
    main()
