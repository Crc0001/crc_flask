"""健康检查接口 /healthz（无需登录，供页面状态指示与云中继探活）。

vendor 模式：仅报本机状态。
client 模式：额外探测我方服务连通性（30 秒缓存，避免浏览器轮询打爆上游）。
"""
import threading
import time
from datetime import datetime

import requests
from flask import Blueprint, current_app, jsonify

from app.config import APP_ROLE, Config

APP_VERSION = Config.APP_VERSION

health_bp = Blueprint("health", __name__)

_UPSTREAM_CACHE = {"ts": 0.0, "ok": None, "message": ""}
_UPSTREAM_TTL = 30
_CACHE_LOCK = threading.Lock()


def _check_upstream():
    """client 模式探测我方服务，返回 (ok, message)。"""
    now = time.time()
    with _CACHE_LOCK:
        if _UPSTREAM_CACHE["ok"] is not None and now - _UPSTREAM_CACHE["ts"] < _UPSTREAM_TTL:
            return _UPSTREAM_CACHE["ok"], _UPSTREAM_CACHE["message"]

    base_url = (current_app.config.get("HWISHAI_API_BASE_URL") or "").rstrip("/")
    machine_token = current_app.config.get("HWISHAI_API_TOKEN") or ""
    if not base_url or not machine_token:
        with _CACHE_LOCK:
            _UPSTREAM_CACHE.update(ts=now, ok=False, message="未配置我方服务地址")
        return False, "未配置我方服务地址"

    ok, message = False, ""
    try:
        resp = requests.get(
            f"{base_url}/healthz",
            headers={"Authorization": f"Bearer {machine_token}"},
            timeout=(3, 3),
        )
        try:
            payload = resp.json()
        except ValueError:
            # 上游 200 但返回非 JSON（如中继的 HTML 错误页）：按不健康处理
            ok, message = False, "我方服务返回内容异常"
        else:
            ok = resp.status_code == 200 and bool(payload.get("success"))
            message = "" if ok else f"HTTP {resp.status_code}"
    except requests.RequestException:
        ok, message = False, "无法连接我方服务"

    with _CACHE_LOCK:
        _UPSTREAM_CACHE.update(ts=now, ok=ok, message=message)
    return ok, message


@health_bp.route("/healthz", methods=["GET"])
def healthz():
    if APP_ROLE == "vendor":
        return jsonify({
            "success": True,
            "status": "ok",
            "role": "vendor",
            "upstream_ok": None,
            "upstream_message": "",
            "version": APP_VERSION,
            "time": datetime.now().isoformat(timespec="seconds"),
        })

    upstream_ok, upstream_message = _check_upstream()
    return jsonify({
        "success": True,
        "status": "ok" if upstream_ok else "degraded",
        "role": "client",
        "upstream_ok": upstream_ok,
        "upstream_message": upstream_message,
        "version": APP_VERSION,
        "time": datetime.now().isoformat(timespec="seconds"),
    })
