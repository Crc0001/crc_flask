import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 开发服务器：默认关闭 debug（避免 Werkzeug 调试器暴露）；需要时 FLASK_DEBUG=1。
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
