"""统一远程调用 API：/api/v1/*

- vendor 模式：recognize 跑本地模型管线；knowledge 查本地知识库。
- client 模式：全部转发我方 vendor 服务（机器令牌鉴权）。
- 两种模式下，调用方都必须带 Bearer Token：
  vendor 侧校验 VENDOR_API_TOKENS 白名单；client 侧校验本地账号 API Token。
"""
import base64
import hmac
import os
from functools import wraps

import requests
from flask import Blueprint, current_app, g, jsonify, request

from app.config import APP_ROLE
from app.models.user import User, audit
from app.services.rate_limit import limiter
from app.services.upload_guard import validate_image_upload

if APP_ROLE == "vendor":
    import cv2
    from app.services.recognition import run_recognition
    from app.services.yolo_service import HWISHAI_CLASSIFIER_MODEL

remote_api_bp = Blueprint("remote_api", __name__, url_prefix="/api/v1")

_RECOGNIZE_LOCK = None
if APP_ROLE == "vendor":
    import threading
    # 识别管线重，vendor 侧同一时刻只跑一个；请求改为快速失败（429）而非无限排队
    _RECOGNIZE_LOCK = threading.Lock()

# vendor 白名单 token 的端点 scope；值可为 {"name":..., "scopes":[...]} 或纯字符串客户名
_KNOWN_SCOPES = {"recognize", "knowledge_search", "knowledge_detail"}


def _token_from_request():
    """仅接受 Authorization: Bearer <token>。

    不再接受 ?token= 查询串回退：token 会进入访问日志/Referer/浏览器历史，泄露面大。
    """
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


def _authorize_request(scope):
    """校验调用方令牌。

    vendor 模式：白名单校验（恒定时间比较 + 可选 scope）。
    client 模式：本地账号 API Token（仅启用账号可用）。
    失败返回 None。
    """
    token = _token_from_request()
    if not token:
        return None
    if APP_ROLE == "vendor":
        allowed = current_app.config.get("VENDOR_API_TOKENS") or {}
        for candidate, entry in allowed.items():
            if not hmac.compare_digest(candidate, token):
                continue
            if isinstance(entry, dict):
                scopes = set(entry.get("scopes") or [])
                if scope in _KNOWN_SCOPES and scope not in scopes:
                    return "forbidden"  # 令牌有效但无该端点权限
                return token, entry.get("name") or "未命名客户"
            return token, str(entry)
        return None
    # client：本地账号 API Token（仅启用账号可用）
    for user in User.query.filter(
        User.is_active.is_(True),
        User.api_token_hash.isnot(None),
    ).all():
        if user.check_api_token(token):
            return user.username, user
    return None


def _caller_display():
    """审计日志里的调用方名称：vendor=客户名；client=账号名。"""
    auth = g.get("api_caller")
    if not auth:
        return "未知"
    if APP_ROLE == "vendor":
        return auth[1] if isinstance(auth, tuple) else str(auth)
    return auth[0]


def require_api_token(scope=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            # 无效令牌尝试限流（每 IP）
            auth_limit, auth_window = current_app.config.get("API_AUTH_RATE_PER_IP", (30, 60))
            if not limiter.allow(f"api:auth:{request.remote_addr}", auth_limit, auth_window):
                return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429

            auth = _authorize_request(scope)
            if auth == "forbidden":
                audit("api_forbidden",
                      f"令牌无权限访问 {scope}（IP {request.remote_addr}）",
                      ip=request.remote_addr)
                return jsonify({"success": False, "message": "该令牌未授权访问此接口"}), 403
            if not auth:
                audit("api_auth_failed", f"无效或缺失 Token（IP {request.remote_addr}）",
                      ip=request.remote_addr)
                return jsonify({"success": False, "message": "API Token 无效或已停用"}), 401
            if APP_ROLE == "client":
                _, user = auth
                if not user.has_perm("api_access"):
                    audit("api_forbidden", f"账号 {user.username} 未授权远程调用API",
                          username=user.username, ip=request.remote_addr)
                    return jsonify({"success": False, "message": "该账号未授权远程调用API"}), 403
            g.api_caller = auth
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _api_rate_limited(config_key, caller_key):
    """按调用方限流，返回 True 表示被限。"""
    limit, window = current_app.config.get(config_key, (0, 0))
    return not limiter.allow(f"api:{config_key}:{caller_key}", limit, window)


def _forward_request(path, files=None, data=None, params=None):
    """client 模式：把请求转发给我方 vendor 服务。"""
    base_url = (current_app.config.get("HWISHAI_API_BASE_URL") or "").rstrip("/")
    machine_token = current_app.config.get("HWISHAI_API_TOKEN") or ""
    if not base_url or not machine_token:
        return jsonify({
            "success": False,
            "message": "服务端未配置我方服务地址（HWISHAI_API_BASE_URL / HWISHAI_API_TOKEN）"
        }), 502
    headers = {"Authorization": f"Bearer {machine_token}"}
    read_timeout = int(current_app.config.get("HWISHAI_API_TIMEOUT", 300))
    # 连接与读取超时分离：连接 5s 快速失败，读取给足识别时间
    timeout = (5, read_timeout)
    try:
        if files is not None:
            resp = requests.post(
                f"{base_url}{path}", files=files, data=data or {},
                headers=headers, timeout=timeout,
            )
        else:
            resp = requests.get(
                f"{base_url}{path}", params=params, headers=headers, timeout=timeout,
            )
    except requests.RequestException as exc:
        current_app.logger.warning("转发我方服务失败（%s%s）: %s", base_url, path, exc)
        return jsonify({"success": False, "message": "无法连接我方服务，请稍后重试"}), 502
    if resp.status_code == 401:
        return jsonify({"success": False, "message": "我方服务鉴权失败（机器令牌无效）"}), 502
    try:
        payload = resp.json()
    except ValueError:
        current_app.logger.warning("我方服务返回非 JSON（%s%s）", base_url, path)
        return jsonify({"success": False, "message": "我方服务返回内容无法解析"}), 502
    return jsonify(payload), resp.status_code


@remote_api_bp.route("/recognize", methods=["POST"])
@require_api_token(scope="recognize")
def recognize():
    """菌种识别：multipart 字段 image；返回 Top3 + 知识库记录ID +（可选）结果图。"""
    if _api_rate_limited("API_RECOGNIZE_RATE", _caller_display()):
        return jsonify({"success": False, "message": "调用过于频繁，请稍后再试"}), 429

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"success": False, "message": "请上传图片文件（字段名 image）"})

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"success": False, "message": "图片内容为空"})

    # 上传安全校验（扩展名白名单 + 魔数 + 尺寸 + 大小），文件名改用服务端生成的安全名
    ok, message, safe_filename = validate_image_upload(file.filename, image_bytes)
    if not ok:
        audit("api_recognize_rejected",
              f"客户端[{_caller_display()}] 上传被拒绝：{message}",
              username=_caller_display(), ip=request.remote_addr)
        return jsonify({"success": False, "message": message})

    if APP_ROLE == "client":
        files = {"image": (safe_filename, image_bytes, "application/octet-stream")}
        data = {"with_result_image": request.form.get("with_result_image", "1")}
        # 客户本地日志：客户系统经本机 API 发起识别（业务数据仍在客户本地）
        audit("api_recognize", f"账号 {_caller_display()} 经本机API调用识别",
              username=_caller_display(), ip=request.remote_addr)
        return _forward_request("/api/v1/recognize", files=files, data=data)

    # ---- vendor：本地管线（同一时刻只跑一个；忙时快速失败 429，不做无限排队） ----
    upload_dir = os.path.join(current_app.root_path, "static", "uploads")
    result_dir = os.path.join(current_app.root_path, "static", "results")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    if not _RECOGNIZE_LOCK.acquire(blocking=False):
        return jsonify({"success": False, "message": "识别服务繁忙，请稍后重试"}), 429
    try:
        result = run_recognition(image_bytes, safe_filename, upload_dir, result_dir)
    except Exception as exc:
        current_app.logger.error("远程识别管线异常: %s", exc, exc_info=True)
        audit("api_recognize_failed",
              f"客户端[{_caller_display()}] 识别管线异常",
              username=_caller_display(), ip=request.remote_addr)
        return jsonify({"success": False, "message": "识别服务内部错误，请稍后重试"}), 500
    finally:
        _RECOGNIZE_LOCK.release()

    if not result.get("ok"):
        audit("api_recognize_failed",
              f"客户端[{_caller_display()}] 识别失败：{result.get('message') or '未知原因'}",
              username=_caller_display(), ip=request.remote_addr)
        return jsonify({"success": False, "message": result.get("message") or "识别失败"})

    top3 = [
        {
            "rank": item["rank"],
            "species_name": item["classifier_species_name"],
            "chinese_name": item["classifier_chinese_name"],
            "confidence": item["classifier_confidence"],
            "matched_strain_id": item["matched_strain_id"],
            "matched_strain_name": item["matched_strain_name"],
            "knowledge_record_id": item["knowledge_record_id"],
            "recognition_model": item["recognition_model"],
        }
        for item in result["top_candidates"]
    ]

    payload = {
        "success": True,
        "message": result["message"],
        "model": f"HwishAI {HWISHAI_CLASSIFIER_MODEL}",
        "top3": top3,
        "plate_crop": result["plate_crop"],
        "image_selection": result["image_selection"],
        "input_risk": result["input_risk"],
        "low_confidence": result["low_confidence"],
    }
    if request.form.get("with_result_image") == "1":
        ok, buf = cv2.imencode(
            ".jpg", result["detection_image"],
            [cv2.IMWRITE_JPEG_QUALITY, 92],
        )
        if ok:
            payload["result_image_base64"] = base64.b64encode(buf.tobytes()).decode("ascii")

    # 我方日志：客户机器调用识别的记录（只能看到 API 层，看不到客户入库数据）
    top1 = top3[0] if top3 else {}
    audit(
        "api_recognize",
        f"客户端[{_caller_display()}] 识别调用 Top1={top1.get('species_name') or '无'}"
        f"（置信度 {top1.get('confidence', 0) * 100:.1f}%）",
        username=_caller_display(),
        ip=request.remote_addr,
    )
    return jsonify(payload)


@remote_api_bp.route("/knowledge/search", methods=["GET"])
@require_api_token(scope="knowledge_search")
def knowledge_search():
    """知识库检索：q/domain/type_strain/genus/environment_only/page/per_page。"""
    if _api_rate_limited("API_KNOWLEDGE_RATE", _caller_display()):
        return jsonify({"success": False, "message": "调用过于频繁，请稍后再试"}), 429

    if APP_ROLE == "client":
        audit("api_knowledge_search",
              f"账号 {_caller_display()} 经本机API检索知识库 q={request.args.get('q', '')[:40]}",
              username=_caller_display(), ip=request.remote_addr)
        return _forward_request(
            "/api/v1/knowledge/search",
            params={k: v for k, v in request.args.items()},
        )

    # ---- vendor：本地 BacDive 库 ----
    from app.models import BacdiveRecord, BacdiveStrainMatch
    from app.routes.strain_showcase import _search_candidates

    query_text = request.args.get("q", "").strip()
    domain = request.args.get("domain", "").strip()
    type_strain = request.args.get("type_strain", "").strip().lower()
    genus = request.args.get("genus", "").strip()
    environment_only = request.args.get("environment_only") == "1"
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 24, type=int), 1), 100)

    query = BacdiveRecord.query
    if domain:
        query = query.filter(BacdiveRecord.domain_name == domain)
    if type_strain in {"yes", "no"}:
        query = query.filter(BacdiveRecord.type_strain == type_strain)
    if genus:
        query = query.filter(BacdiveRecord.genus_name.like(f"%{genus}%"))
    if environment_only:
        query = query.join(BacdiveStrainMatch).distinct()

    query_without_search = query
    pagination = None
    if query_text:
        for candidate in _search_candidates(query_without_search, query_text):
            pagination = candidate.order_by(BacdiveRecord.bacdive_id.asc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            if pagination.total:
                break
    if pagination is None:
        pagination = query_without_search.order_by(
            BacdiveRecord.bacdive_id.asc()
        ).paginate(page=page, per_page=per_page, error_out=False)

    records = []
    for record in pagination.items:
        description = (record.description or "").strip()
        records.append({
            "record_id": record.id,
            "bacdive_id": record.bacdive_id,
            "dsm_number": record.dsm_number or "",
            "domain_name": record.domain_name or "",
            "family_name": record.family_name or "",
            "genus_name": record.genus_name or "",
            "species_name": record.species_name or "",
            "species_name_zh": record.species_name_zh or "",
            "full_scientific_name": record.full_scientific_name or "",
            "strain_designation": record.strain_designation or "",
            "type_strain": record.type_strain or "",
            "description_short": description[:200],
        })

    audit(
        "api_knowledge_search",
        f"客户端[{_caller_display()}] 检索知识库 q={query_text[:40]} 命中 {pagination.total} 条",
        username=_caller_display(),
        ip=request.remote_addr,
    )
    return jsonify({
        "success": True,
        "total": pagination.total,
        "pages": pagination.pages or 1,
        "page": page,
        "per_page": per_page,
        "records": records,
    })


@remote_api_bp.route("/knowledge/<int:record_id>", methods=["GET"])
@require_api_token(scope="knowledge_detail")
def knowledge_detail(record_id):
    """菌种知识库详情。"""
    if _api_rate_limited("API_KNOWLEDGE_RATE", _caller_display()):
        return jsonify({"success": False, "message": "调用过于频繁，请稍后再试"}), 429

    if APP_ROLE == "client":
        audit("api_knowledge_detail",
              f"账号 {_caller_display()} 经本机API查看知识库详情 #{record_id}",
              username=_caller_display(), ip=request.remote_addr)
        return _forward_request(f"/api/v1/knowledge/{record_id}")

    # ---- vendor：本地 BacDive 库 ----
    from app.models import BacdiveRecord
    from app.routes.strain_showcase import (
        _clean_json,
        _find_silva_sequences,
        _parse_json_text,
    )

    record = BacdiveRecord.query.filter_by(id=record_id).first()
    if not record:
        return jsonify({"success": False, "message": "知识库记录不存在"}), 404

    data_sections = [
        ("培养基", _clean_json(record.culture_medium)),
        ("培养温度", _clean_json(record.culture_temp)),
        ("培养 pH", _clean_json(record.culture_ph)),
        ("形态学", _clean_json(record.morphology)),
        ("生理与代谢", _clean_json(record.physiology)),
        ("分离与环境信息", _clean_json(record.isolation_info)),
        ("安全性", _clean_json(record.safety_info)),
        ("序列信息", _clean_json(record.sequence_info)),
        ("文献", _clean_json(record.literature_info)),
    ]
    taxonomy = [
        ("域", record.domain_name),
        ("门", record.phylum_name),
        ("纲", record.class_name),
        ("目", record.order_name),
        ("科", record.family_name),
        ("属", record.genus_name),
        ("种", record.species_name),
    ]
    silva = []
    try:
        for seq in _find_silva_sequences(record):
            silva.append({
                "organism_name": seq.organism_name or "",
                "accession": seq.accession or "",
                "sequence_length": seq.sequence_length,
            })
    except Exception:
        silva = []

    audit(
        "api_knowledge_detail",
        f"客户端[{_caller_display()}] 查看知识库详情 #{record_id} "
        f"{record.species_name or ''}",
        username=_caller_display(),
        ip=request.remote_addr,
    )
    return jsonify({
        "success": True,
        "record": {
            "record_id": record.id,
            "bacdive_id": record.bacdive_id,
            "dsm_number": record.dsm_number or "",
            "species_name": record.species_name or "",
            "species_name_zh": record.species_name_zh or "",
            "full_scientific_name": record.full_scientific_name or "",
            "strain_designation": record.strain_designation or "",
            "type_strain": record.type_strain or "",
            "description": record.description or "",
            "keywords": record.keywords or "",
            "strain_history": _parse_json_text(record.strain_history),
            "taxonomy": [list(item) for item in taxonomy],
            "data_sections": [list(item) for item in data_sections],
            "silva_sequences": silva,
        },
    })
