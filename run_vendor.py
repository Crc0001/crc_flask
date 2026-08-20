"""我方模型机生产启动入口（waitress）。

使用方式：
    python run_vendor.py

端口与监听地址来自配置（SERVER_HOST/SERVER_PORT，默认 0.0.0.0:8355）。
仅在本机/内网运行，对外出口由云中继（frp/Caddy）负责，勿直接暴露公网。

安全策略：生产模式拒绝使用随机兜底的会话密钥与默认数据库连接，
必须由 instance\\config.py（或环境变量）显式提供。
"""
import os
import sys

os.environ.setdefault("HWISHAI_APP_ROLE", "vendor")

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
    if problems:
        print("[ERROR] 生产配置不完整，拒绝启动：", flush=True)
        for problem in problems:
            print(f"  - {problem}", flush=True)
        print("请在 instance\\config.py 配置 SECRET_KEY 与 SQLALCHEMY_DATABASE_URI 后再启动。",
              flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _check_production_config()
    host = app.config.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVER_PORT") or app.config.get("SERVER_PORT", 8355))
    print(f"[HwishAI] vendor 服务启动: http://{host}:{port}", flush=True)
    serve(app, host=host, port=port, threads=4, channel_timeout=600)
