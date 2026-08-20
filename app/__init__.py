import hmac
import os
import secrets
from datetime import timedelta

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user

from app.config import Config
from app.extensions import db, login_manager

# client 模式不导入 MALDI 蓝图（依赖 matplotlib 等非业务包，且模块暂不出客户端）
if Config.APP_ROLE == "vendor":
    from app.routes.maldi_matching import maldi_matching_bp

from app.routes.admin_accounts import admin_accounts_bp
from app.routes.admin_console import admin_console_bp
from app.routes.ai_detection import ai_detection_bp
from app.routes.analysis import analysis_bp
from app.routes.auth import auth_bp
from app.routes.health import health_bp
from app.routes.main import main_bp
from app.routes.remote_api import remote_api_bp
from app.routes.strain_db import strain_db_bp
from app.routes.strain_showcase import strain_showcase_bp

# 无需登录会话的端点（remote_api 用 Token 自管鉴权；healthz 公开供探活）
_PUBLIC_ENDPOINTS = {"static", "auth.login", "auth.logout", "health.healthz"}

# 蓝图 -> 功能权限码（页面与业务 API 统一按功能授权）
_BLUEPRINT_PERMISSION = {
    "ai_detection": "ai_detection",
    "strain_db": "strain_db",
    "analysis": "analysis",
    "strain_showcase": "strain_showcase",
}
if Config.APP_ROLE == "vendor":
    _BLUEPRINT_PERMISSION["maldi_matching"] = "maldi_matching"


def _bootstrap_accounts(app):
    """首次启动自动创建初始账号/权限种子并建账号相关表。

    安全策略（对应调研报告 V-04）：
    - 首次引导成功后写 instance/.bootstrap_done 标记；之后若引导账号被删除，
      拒绝再自动重建（防止"删号+重启=默认口令复活"后门）；
    - 账号不存在且其初始密码未显式配置（环境变量或 instance/config.py）时，
      拒绝创建（不再内置可预知的默认口令）。
    """
    from app.models.user import (
        ROLE_ADMIN,
        ROLE_OPERATOR,
        ROLE_SUPER_ADMIN,
        AuditLog,
        RolePermission,
        User,
        default_role_permissions,
    )

    # 只建账号/权限/审计表（客户端不建知识库等模型表）
    for table in (User.__table__, AuditLog.__table__, RolePermission.__table__):
        table.create(db.engine, checkfirst=True)

    marker_path = os.path.join(app.instance_path, ".bootstrap_done")
    already_bootstrapped = os.path.exists(marker_path)

    def _ensure_bootstrap_user(username, display_name, role, password, explicit,
                               password_env_key, must_change):
        if User.query.filter_by(username=username).first():
            return
        if already_bootstrapped:
            raise RuntimeError(
                f"引导账号 {username} 不存在，但首次引导已完成（instance/.bootstrap_done 存在）。"
                "为防默认口令复活，已拒绝自动重建；如确需重建，请删除该标记文件、显式配置 "
                f"{password_env_key} 后重启。"
            )
        if not explicit or not password:
            raise RuntimeError(
                f"初始账号 {username} 不存在，且未显式配置其初始密码"
                f"（请设置环境变量 {password_env_key} 或在 instance/config.py 中配置）。"
                "出于安全考虑，系统不再使用内置默认口令创建账号。"
            )
        user = User(
            username=username,
            display_name=display_name,
            role=role,
            must_change_password=must_change,
        )
        user.set_password(password)
        db.session.add(user)

    _ensure_bootstrap_user(
        app.config.get("BOOTSTRAP_SUPERADMIN_USERNAME", "hwishai"),
        "HwishAI 厂家",
        ROLE_SUPER_ADMIN,
        app.config.get("BOOTSTRAP_SUPERADMIN_PASSWORD", ""),
        app.config.get("BOOTSTRAP_SUPERADMIN_PASSWORD_EXPLICIT", False),
        "BOOTSTRAP_SUPERADMIN_PASSWORD",
        must_change=False,
    )
    _ensure_bootstrap_user(
        app.config.get("BOOTSTRAP_ADMIN_USERNAME", "admin"),
        "客户管理员",
        ROLE_ADMIN,
        app.config.get("BOOTSTRAP_ADMIN_PASSWORD", ""),
        app.config.get("BOOTSTRAP_ADMIN_PASSWORD_EXPLICIT", False),
        "BOOTSTRAP_ADMIN_PASSWORD",
        must_change=True,
    )

    db.session.commit()

    # 权限种子：admin / operator 首次给全量默认权限（super_admin 恒为全部，不入表）
    include_maldi = Config.APP_ROLE == "vendor"
    for role in (ROLE_ADMIN, ROLE_OPERATOR):
        if not RolePermission.query.filter_by(role=role).first():
            for code in default_role_permissions(include_maldi=include_maldi):
                db.session.add(RolePermission(role=role, permission=code))
    db.session.commit()

    # 标记首次引导已完成（写失败不阻断启动，仅失去"防复活"保护）
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write("bootstrapped\n")
    except OSError:
        pass


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    if not Config.SECRET_KEY_EXPLICIT:
        app.logger.warning(
            "SECRET_KEY 未显式配置，已使用进程级随机密钥（重启后会话失效但不可伪造）。"
            "生产部署请在 instance/config.py 配置随机 SECRET_KEY。"
        )

    # 会话安全与时长
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(Config.SESSION_COOKIE_SECURE),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_DURATION=timedelta(days=14),
    )

    db.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(admin_accounts_bp)
    app.register_blueprint(admin_console_bp)
    app.register_blueprint(remote_api_bp)
    app.register_blueprint(ai_detection_bp)
    app.register_blueprint(strain_db_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(strain_showcase_bp)
    if Config.APP_ROLE == "vendor":
        app.register_blueprint(maldi_matching_bp)

    def _get_csrf_token():
        """会话级 CSRF Token（登录成功后保持不变，便于前端 meta 标签复用）。"""
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = _get_csrf_token

    @app.before_request
    def _require_login():
        # 页面与业务 API 统一要求登录会话；/api/v1/* 走 Token 鉴权
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return None
        if request.endpoint and request.endpoint.startswith("remote_api."):
            return None
        if current_user.is_authenticated:
            # 首次登录/被重置密码后强制改密：除改密/登出/静态资源外一律拦截
            if getattr(current_user, "must_change_password", False):
                if request.endpoint not in (
                    "auth.change_password",
                    "auth.logout",
                    "static",
                    "health.healthz",
                ):
                    if request.path.startswith("/api/"):
                        return jsonify({
                            "success": False,
                            "message": "首次登录或密码被重置，请先修改密码",
                        }), 403
                    return redirect(url_for("auth.change_password"))
            return None
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "未登录或会话已过期"}), 401
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))

    @app.before_request
    def _check_permission():
        """功能权限拦截：页面/业务 API 按蓝图对应权限码校验（管理控制台走角色校验）。"""
        if not current_user.is_authenticated:
            return None
        if not request.endpoint:
            return None
        blueprint_name = request.endpoint.split(".")[0]
        code = _BLUEPRINT_PERMISSION.get(blueprint_name)
        if not code:
            return None
        from app.models.user import user_has_permission
        if user_has_permission(current_user, code):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "无权限访问该功能"}), 403
        abort(403)

    @app.before_request
    def _csrf_protect():
        """CSRF 防护：状态变更请求必须携带会话 CSRF Token（表单域 csrf_token 或
        X-CSRF-Token 头，前端全局 fetch 包装会自动注入）。

        豁免：GET/HEAD/OPTIONS；static/healthz；remote_api（Bearer 自管）；
        /api/*（业务 API，SameSite=Lax + 同源 fetch 头注入已覆盖）。
        """
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        if not request.endpoint:
            return None
        if request.endpoint in ("static", "health.healthz"):
            return None
        if request.endpoint.startswith("remote_api."):
            return None
        if request.path.startswith("/api/"):
            return None

        expected = session.get("_csrf_token") or ""
        supplied = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("csrf_token")
            or ""
        )
        if expected and supplied and hmac.compare_digest(expected, supplied):
            return None

        if request.path.startswith(("/admin/", "/strain_db/")):
            return jsonify({"success": False, "message": "页面已过期，请刷新后重试"}), 400
        return render_template("403.html"), 403

    @app.errorhandler(403)
    def _forbidden(error):
        return render_template("403.html"), 403

    @app.errorhandler(413)
    def _too_large(error):
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "message": "上传内容过大（超过服务器大小限制），请压缩或更换图片",
            }), 413
        return render_template("413.html"), 413

    @app.errorhandler(404)
    def _not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "接口不存在"}), 404
        return render_template("404.html"), 404

    @app.after_request
    def _security_headers(response):
        """统一安全响应头（调研报告 V-01/L-08）：阻断 MIME 嗅探、限制嵌入与对象加载。"""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # 页面存在内联样式/脚本与外部 CDN（分析页 Chart.js、知识库外链图），
        # 采用"默认同源 + 白名单放行"的中等强度 CSP。
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https:; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: http: https:; "
            "connect-src 'self' https:; "
            "font-src 'self' data: http: https:; "
            "object-src 'none'; frame-ancestors 'self'; base-uri 'self'",
        )
        return response

    with app.app_context():
        _bootstrap_accounts(app)

    return app
