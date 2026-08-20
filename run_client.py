"""客户本地生产启动入口（waitress + Windows 服务）。

使用方式：
    venv\\Scripts\\python.exe run_client.py

端口与监听地址来自配置（SERVER_HOST/SERVER_PORT，默认 0.0.0.0:8856），
也可用环境变量 SERVER_PORT 覆盖。此入口不依赖 torch/模型，仅跑 client 业务。

安全策略：生产模式拒绝使用默认/随机兜底的密钥与连接配置，
必须由 04_configure.py 生成的 instance\\config.py（或环境变量）显式提供。
"""
import os
import sys

os.environ.setdefault("HWISHAI_APP_ROLE", "client")

from waitress import serve

from app import create_app
from app.config import Config

app = create_app()


def _check_production_config():
    problems = []
    if not Config.SECRET_KEY_EXPLICIT:
        problems.append("SECRET_KEY 未显式配置（会话密钥不可随机兜底）")
    if not Config.SQLALCHEMY_DATABASE_URI_EXPLICIT:
        problems.append("SQLALCHEMY_DATABASE_URI 未显式配置（数据库连接）")
    if not Config.HWISHAI_API_BASE_URL_EXPLICIT or not Config.HWISHAI_API_BASE_URL:
        problems.append("HWISHAI_API_BASE_URL 未显式配置（我方服务地址）")
    if not Config.HWISHAI_API_TOKEN_EXPLICIT or not Config.HWISHAI_API_TOKEN:
        problems.append("HWISHAI_API_TOKEN 未显式配置（机器令牌）")
    if problems:
        print("[ERROR] 生产配置不完整，拒绝启动：", flush=True)
        for problem in problems:
            print(f"  - {problem}", flush=True)
        print("请先运行 04_configure.py 生成 instance\\config.py（或补齐环境变量）后再启动。",
              flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _check_production_config()
    host = app.config.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVER_PORT") or app.config.get("SERVER_PORT", 8856))
    print(f"[HwishAI] client 服务启动: http://{host}:{port}", flush=True)
    serve(app, host=host, port=port, threads=8, channel_timeout=300)
