from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, login_manager
from app.models.user import User, audit, is_locked, register_login_failure
from app.services.rate_limit import limiter

auth_bp = Blueprint("auth", __name__)

login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def _safe_next(target):
    """只允许站内相对路径跳转，防开放重定向。

    同时拒绝含反斜杠的值（浏览器会把路径中的 \\ 归一化为 /，
    `/\evil.com` 会变成协议相对跳转）。
    """
    if not target:
        return None
    if "\\" in target or "://" in target or target.startswith("//"):
        return None
    return target if target.startswith("/") else "/"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "1"

        user = User.query.filter_by(username=username).first()

        # 锁定检查提前：锁定期间继续提交错误密码不再延长 locked_until（防无限续锁）
        if user and is_locked(user):
            flash("登录失败次数过多，账号已临时锁定，请稍后再试", "error")
            return render_template("auth/login.html", next_url=request.args.get("next"))

        if not user or not user.check_password(password):
            # 限流仅统计失败尝试（成功登录不计入，避免正常使用被误伤）
            fail_limit, fail_window = current_app.config.get("LOGIN_RATE_FAIL_PER_USER", (60, 300))
            fail_key = f"login:fail:{request.remote_addr}:{username}"
            if not limiter.allow(fail_key, fail_limit, fail_window):
                flash("该账号失败次数过多，请稍后再试", "error")
                return render_template("auth/login.html", next_url=request.args.get("next"))

            per_ip_limit, per_ip_window = current_app.config.get("LOGIN_RATE_PER_IP", (200, 60))
            if not limiter.allow(f"login:ip:{request.remote_addr}", per_ip_limit, per_ip_window):
                flash("尝试过于频繁，请稍后再试", "error")
                return render_template("auth/login.html", next_url=request.args.get("next"))

            if user:
                register_login_failure(user)
                db.session.commit()
                audit("login_failed", f"密码错误：{username}", username=username,
                      ip=request.remote_addr)
            flash("用户名或密码错误", "error")
            return render_template("auth/login.html", next_url=request.args.get("next"))

        if not user.is_active:
            # 统一文案，避免暴露账号状态（枚举）
            flash("用户名或密码错误", "error")
            return render_template("auth/login.html", next_url=request.args.get("next"))

        # 会话固定防御：登录成功即轮换会话；保留 CSRF Token 以便页面继续使用
        csrf_token = session.get("_csrf_token")
        session.clear()
        if csrf_token:
            session["_csrf_token"] = csrf_token

        login_user(user, remember=remember)
        user.login_failed_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now()
        db.session.commit()
        audit("login", f"登录成功：{username}", username=username,
              ip=request.remote_addr)

        if user.must_change_password:
            return redirect(url_for("auth.change_password"))

        next_url = _safe_next(request.args.get("next"))
        return redirect(next_url or url_for("main.index"))

    return render_template("auth/login.html", next_url=request.args.get("next"))


@auth_bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        audit("logout", f"退出登录：{current_user.username}",
              username=current_user.username, ip=request.remote_addr)
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_password = request.form.get("old_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not current_user.check_password(old_password):
            flash("当前密码不正确", "error")
            return render_template("auth/change_password.html")
        if len(new_password) < 8:
            flash("新密码至少 8 位", "error")
            return render_template("auth/change_password.html")
        if new_password != confirm_password:
            flash("两次输入的新密码不一致", "error")
            return render_template("auth/change_password.html")
        if new_password == old_password:
            flash("新密码不能与当前密码相同", "error")
            return render_template("auth/change_password.html")

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()
        audit("change_password", f"修改密码：{current_user.username}",
              username=current_user.username, ip=request.remote_addr)
        flash("密码修改成功", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/change_password.html")
