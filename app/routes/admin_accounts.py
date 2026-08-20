from flask import (
    Blueprint,
    abort,
    jsonify,
    render_template,
    request,
)
from flask_login import current_user, login_required
from functools import wraps

from app.extensions import db
from app.models.user import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SUPER_ADMIN,
    User,
    audit,
    generate_api_token,
)

admin_accounts_bp = Blueprint("admin_accounts", __name__)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            if request.path.startswith("/admin/accounts/"):
                return jsonify({"success": False, "message": "无权限执行该操作"}), 403
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _scope_error(target):
    """校验当前用户能否操作目标账号，返回错误信息或 None。"""
    if target.role == ROLE_SUPER_ADMIN:
        return "不能操作超级管理员账号"
    if current_user.is_super_admin:
        return None
    if current_user.role == ROLE_ADMIN and target.role == ROLE_OPERATOR:
        return None
    return "无权限操作该账号"


def _valid_new_role():
    role = (request.form.get("role") or ROLE_OPERATOR).strip()
    if current_user.is_super_admin:
        allowed = (ROLE_ADMIN, ROLE_OPERATOR)
    else:
        allowed = (ROLE_OPERATOR,)
    return role if role in allowed else None


@admin_accounts_bp.route("/admin/accounts", methods=["GET"])
@admin_required
def index():
    if current_user.is_super_admin:
        users = User.query.order_by(User.id).all()
    else:
        # 客户管理员看不到厂家超级管理员账号
        users = User.query.filter(User.role != ROLE_SUPER_ADMIN).order_by(User.id).all()
    return render_template("admin/accounts.html", users=users)


@admin_accounts_bp.route("/admin/accounts/create", methods=["POST"])
@admin_required
def create():
    username = (request.form.get("username") or "").strip()
    display_name = (request.form.get("display_name") or "").strip() or username
    password = request.form.get("password") or ""
    role = _valid_new_role()

    if not username:
        return jsonify({"success": False, "message": "用户名不能为空"}), 400
    if role is None:
        return jsonify({"success": False, "message": "无权创建该角色的账号"}), 403
    if len(password) < 8:
        return jsonify({"success": False, "message": "密码至少 8 位"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "用户名已存在"}), 400

    user = User(username=username, display_name=display_name, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    audit("account_create", f"创建账号 {username}（角色 {user.role_label}）",
          username=current_user.username, ip=request.remote_addr)
    return jsonify({"success": True, "message": f"账号 {username} 创建成功"})


@admin_accounts_bp.route("/admin/accounts/<int:user_id>/update", methods=["POST"])
@admin_required
def update(user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"success": False, "message": "账号不存在"}), 404

    error = _scope_error(target)
    if error:
        return jsonify({"success": False, "message": error}), 403

    display_name = (request.form.get("display_name") or "").strip()
    is_active = request.form.get("is_active") == "1"
    # 表单缺省 role 时保持原角色：修复"停用/启用按钮只传 is_active 导致
    # admin 被静默降级为 operator"的逻辑漏洞（调研报告 V-07）。
    role = (request.form.get("role") or target.role).strip()
    if current_user.is_super_admin:
        allowed_roles = (ROLE_ADMIN, ROLE_OPERATOR)
    else:
        allowed_roles = (ROLE_OPERATOR,)
    if role not in allowed_roles:
        return jsonify({"success": False, "message": "无权设置该角色"}), 403
    if not is_active and target.id == current_user.id:
        return jsonify({"success": False, "message": "不能停用自己的账号"}), 400

    changed = []
    if display_name and display_name != target.display_name:
        target.display_name = display_name
        changed.append(f"显示名→{display_name}")
    if role != target.role:
        target.role = role
        changed.append(f"角色→{target.role_label}")
    if is_active != target.is_active:
        target.is_active = is_active
        changed.append("启用" if is_active else "停用")
    db.session.commit()
    audit("account_update", f"更新账号 {target.username}：{', '.join(changed) or '无变化'}",
          username=current_user.username, ip=request.remote_addr)
    return jsonify({"success": True, "message": f"账号 {target.username} 已更新"})


@admin_accounts_bp.route("/admin/accounts/<int:user_id>/reset_password", methods=["POST"])
@admin_required
def reset_password(user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"success": False, "message": "账号不存在"}), 404

    error = _scope_error(target)
    if error:
        return jsonify({"success": False, "message": error}), 403

    password = request.form.get("password") or ""
    force_change = request.form.get("force_change") == "1"
    if len(password) < 8:
        return jsonify({"success": False, "message": "新密码至少 8 位"}), 400

    target.set_password(password)
    target.must_change_password = force_change
    # 重置密码同时解除锁定（避免"密码已重置但账号仍被锁"的现场事故）
    target.locked_until = None
    target.login_failed_count = 0
    db.session.commit()
    audit("account_reset_password", f"重置账号 {target.username} 的密码（首次登录强制改密：{force_change}）",
          username=current_user.username, ip=request.remote_addr)
    return jsonify({"success": True, "message": f"账号 {target.username} 密码已重置"})


@admin_accounts_bp.route("/admin/accounts/<int:user_id>/reset_token", methods=["POST"])
@admin_required
def reset_token(user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"success": False, "message": "账号不存在"}), 404

    error = _scope_error(target)
    if error:
        return jsonify({"success": False, "message": error}), 403

    token = generate_api_token()
    target.set_api_token(token)
    db.session.commit()
    audit("account_reset_token", f"重置账号 {target.username} 的 API Token",
          username=current_user.username, ip=request.remote_addr)
    return jsonify({
        "success": True,
        "message": "Token 已重新生成，请立即保存（仅显示这一次）",
        "token": token,
    })


@admin_accounts_bp.route("/admin/accounts/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete(user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"success": False, "message": "账号不存在"}), 404

    error = _scope_error(target)
    if error:
        return jsonify({"success": False, "message": error}), 403
    if target.id == current_user.id:
        return jsonify({"success": False, "message": "不能删除自己的账号"}), 400

    username = target.username
    db.session.delete(target)
    db.session.commit()
    audit("account_delete", f"删除账号 {username}",
          username=current_user.username, ip=request.remote_addr)
    return jsonify({"success": True, "message": f"账号 {username} 已删除"})
