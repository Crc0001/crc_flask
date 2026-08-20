"""管理控制台（仅管理员角色可见）：概览 / 权限管理 / 操作日志。"""
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from functools import wraps

from app.config import APP_ROLE
from app.extensions import db
from app.models.sample import Sample
from app.models.user import (
    AuditLog,
    FUNCTION_PERMISSIONS,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPER_ADMIN,
    User,
    audit,
    get_role_permissions,
    set_role_permissions,
)

admin_console_bp = Blueprint("admin_console", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            if request.path.startswith("/admin/"):
                return jsonify({"success": False, "message": "无权限执行该操作"}), 403
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _editable_roles():
    """当前管理员可以编辑的角色列表。"""
    if current_user.is_super_admin:
        return [ROLE_ADMIN, ROLE_OPERATOR]
    return [ROLE_OPERATOR]


def _visible_permissions():
    """按部署角色过滤功能权限列表（client 端无 MALDI）。"""
    items = []
    for code, label in FUNCTION_PERMISSIONS.items():
        if code == "maldi_matching" and APP_ROLE != "vendor":
            continue
        items.append((code, label))
    return items


@admin_console_bp.route("/", methods=["GET"])
@admin_required
def index():
    """概览页：账号/业务统计 + 最近登录。"""
    user_count = User.query.count()
    active_count = User.query.filter_by(is_active=True).count()
    try:
        sample_count = Sample.query.count()
        week_ago = datetime.now() - timedelta(days=7)
        detect_week = (
            Sample.query.filter(Sample.last_detect_time >= week_ago).count()
        )
    except Exception as exc:
        # client 新装库可能尚无 sample 表（引导只建账号表）：统计容错为 0
        current_app.logger.warning("概览统计 sample 表查询失败: %s", exc)
        sample_count = 0
        detect_week = 0
    stats = {
        "user_count": user_count,
        "active_count": active_count,
        "sample_count": sample_count,
        "detect_week": detect_week,
        "maldi_count": None,
    }
    if APP_ROLE == "vendor":
        try:
            from app.models.maldi_reference import MaldiReference
            stats["maldi_count"] = MaldiReference.query.count()
        except Exception:
            stats["maldi_count"] = None

    recent_logins = (
        AuditLog.query.filter_by(action="login")
        .order_by(AuditLog.id.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/console.html",
        stats=stats,
        recent_logins=recent_logins,
        active="index",
    )


@admin_console_bp.route("/permissions", methods=["GET"])
@admin_required
def permissions():
    """权限管理页：按角色勾选功能权限（矩阵）。"""
    roles = []
    for role in _editable_roles():
        roles.append({
            "code": role,
            "label": {"admin": "管理员", "operator": "操作员"}.get(role, role),
            "granted": get_role_permissions(role),
        })
    return render_template(
        "admin/permissions.html",
        roles=roles,
        permission_items=_visible_permissions(),
        active="permissions",
    )


@admin_console_bp.route("/permissions/save", methods=["POST"])
@admin_required
def permissions_save():
    """保存角色权限（整体替换）。"""
    changed = []
    for role in _editable_roles():
        codes = request.form.getlist(f"perm_{role}")
        codes = [c for c in codes if c in FUNCTION_PERMISSIONS]
        set_role_permissions(role, codes)
        changed.append(f"{role}: {','.join(codes) or '无'}")
    db.session.commit()
    audit("permission_update", f"更新角色权限：{'；'.join(changed)}",
          username=current_user.username, ip=request.remote_addr)
    return jsonify({"success": True, "message": "权限已保存"})


@admin_console_bp.route("/logs", methods=["GET"])
@admin_required
def logs():
    """操作日志：登录/账号/权限等审计记录。"""
    username = request.args.get("username", "").strip()
    action = request.args.get("action", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    page = request.args.get("page", 1, type=int)

    query = AuditLog.query
    if username:
        query = query.filter(AuditLog.username.like(f"%{username}%"))
    if action:
        query = query.filter_by(action=action)
    try:
        if date_from:
            query = query.filter(AuditLog.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(AuditLog.created_at < end)
    except ValueError:
        pass

    pagination = query.order_by(AuditLog.id.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    actions = [row[0] for row in
               db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    return render_template(
        "admin/logs.html",
        logs=pagination.items,
        pagination=pagination,
        actions=actions,
        filters={"username": username, "action": action,
                 "date_from": date_from, "date_to": date_to},
        active="logs",
    )
