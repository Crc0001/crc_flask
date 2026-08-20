import json
import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# 双端模式：vendor=我方（本地模型+本地知识库）; client=客户（无模型，代理调用我方）
APP_ROLE = (os.environ.get("HWISHAI_APP_ROLE") or "vendor").strip().lower()
if APP_ROLE not in ("vendor", "client"):
    APP_ROLE = "vendor"


def _read_instance_config():
    """读取 instance/config.py（部署现场覆盖默认值，可选文件）。"""
    cfg = {}
    path = os.path.join(PROJECT_ROOT, "instance", "config.py")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            exec(compile(f.read(), path, "exec"), cfg)
    return cfg


_INSTANCE = _read_instance_config()


def _get(key, default):
    """优先级：环境变量 > instance/config.py > 默认值。"""
    return os.environ.get(key, _INSTANCE.get(key, default))


def _explicit(key):
    """某项配置是否被显式提供（环境变量或 instance/config.py）。"""
    return key in os.environ or key in _INSTANCE


def _get_int_tuple(key, default):
    """读取 "(上限, 秒)" 形式的限流配置，支持 "limit,window" 字符串。"""
    raw = os.environ.get(key, _INSTANCE.get(key))
    if raw is None:
        return default
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        try:
            return (int(raw[0]), int(raw[1]))
        except (TypeError, ValueError):
            return default
    if isinstance(raw, str) and "," in raw:
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) == 2:
            try:
                return (int(parts[0]), int(parts[1]))
            except ValueError:
                return default
    return default


def _parse_vendor_tokens(raw):
    """vendor 侧允许接入的客户端机器令牌。

    支持：instance/config.py 里的 dict/JSON 字符串，
    或环境变量 HWISHAI_VENDOR_TOKENS 的 JSON：
    {"<token>": "客户A", ...}
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if k}
    try:
        data = json.loads(str(raw))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if k}
    except (TypeError, ValueError):
        pass
    return {}


class Config:
    APP_ROLE = APP_ROLE
    APP_VERSION = _get("HWISHAI_APP_VERSION", "1.0.0")
    # 会话密钥：每台部署在 instance/config.py 里放随机值（python -c "import secrets;print(secrets.token_hex(32))"）。
    # 未显式配置时退回"进程级随机值"：会话不可伪造，但每次重启会失效（生产入口会拒绝启动）。
    SECRET_KEY_EXPLICIT = _explicit("SECRET_KEY")
    SECRET_KEY = _get("SECRET_KEY", "") or secrets.token_hex(32)

    SQLALCHEMY_DATABASE_URI_EXPLICIT = _explicit("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_DATABASE_URI = _get(
        "SQLALCHEMY_DATABASE_URI",
        "mysql+pymysql://root:123456@localhost/crc_ai",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    # 上传防护：整个请求体上限 20MB（超限返回 413）；单文件上限见 services/upload_guard.py
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # 内网默认 HTTP 明文，Secure 置位会导致会话 Cookie 无法传输；接入 HTTPS 中继后置 1。
    SESSION_COOKIE_SECURE = _get("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True

    # ---- 进程内限流（元组 = (窗口内次数上限, 窗口秒数)，0 表示不限） ----
    # 登录：每 IP 请求次数上限（防表单轰炸）
    LOGIN_RATE_PER_IP = _get_int_tuple("LOGIN_RATE_PER_IP", (200, 60))
    # 登录失败：每 IP+用户名 失败次数上限（与账号锁定互补，防分布式猜测）
    LOGIN_RATE_FAIL_PER_USER = _get_int_tuple("LOGIN_RATE_FAIL_PER_USER", (60, 300))
    # /api/v1：无效令牌尝试（每 IP）
    API_AUTH_RATE_PER_IP = _get_int_tuple("API_AUTH_RATE_PER_IP", (30, 60))
    # /api/v1/recognize（每个调用方令牌）
    API_RECOGNIZE_RATE = _get_int_tuple("API_RECOGNIZE_RATE", (20, 60))
    # /api/v1/knowledge/*（每个调用方令牌）
    API_KNOWLEDGE_RATE = _get_int_tuple("API_KNOWLEDGE_RATE", (120, 60))

    # 生产启动（waitress）：客户机 8856 / 我方 8355
    SERVER_HOST = _get("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(_get("SERVER_PORT", 8856 if APP_ROLE == "client" else 8355))

    # ---- client 模式：我方模型/知识库服务地址与机器令牌 ----
    HWISHAI_API_BASE_URL_EXPLICIT = _explicit("HWISHAI_API_BASE_URL")
    HWISHAI_API_TOKEN_EXPLICIT = _explicit("HWISHAI_API_TOKEN")
    HWISHAI_API_BASE_URL = str(_get("HWISHAI_API_BASE_URL", "")).rstrip("/")
    HWISHAI_API_TOKEN = _get("HWISHAI_API_TOKEN", "")
    HWISHAI_API_TIMEOUT = int(_get("HWISHAI_API_TIMEOUT", 300))

    # ---- vendor 模式：允许接入的客户端机器令牌白名单 ----
    # 环境变量 HWISHAI_VENDOR_TOKENS（JSON）或 instance/config.py 的 VENDOR_API_TOKENS（dict）
    VENDOR_API_TOKENS = _parse_vendor_tokens(
        _get("HWISHAI_VENDOR_TOKENS", _get("VENDOR_API_TOKENS", {}))
    )

    # ---- 首次启动自动创建的初始账号 ----
    # 安全策略：账号不存在且密码未显式配置时，_bootstrap_accounts 会拒绝创建（见 app/__init__.py）。
    BOOTSTRAP_SUPERADMIN_USERNAME = _get("BOOTSTRAP_SUPERADMIN_USERNAME", "hwishai")
    BOOTSTRAP_SUPERADMIN_PASSWORD_EXPLICIT = _explicit("BOOTSTRAP_SUPERADMIN_PASSWORD")
    BOOTSTRAP_SUPERADMIN_PASSWORD = _get("BOOTSTRAP_SUPERADMIN_PASSWORD", "")
    BOOTSTRAP_ADMIN_USERNAME = _get("BOOTSTRAP_ADMIN_USERNAME", "admin")
    BOOTSTRAP_ADMIN_PASSWORD_EXPLICIT = _explicit("BOOTSTRAP_ADMIN_PASSWORD")
    BOOTSTRAP_ADMIN_PASSWORD = _get("BOOTSTRAP_ADMIN_PASSWORD", "")
