import hmac
import secrets
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"

ROLE_LABELS = {
    ROLE_SUPER_ADMIN: "超级管理员",
    ROLE_ADMIN: "管理员",
    ROLE_OPERATOR: "操作员",
}

MAX_LOGIN_FAILURES = 5
LOCKOUT_MINUTES = 10


class User(db.Model):
    __tablename__ = "sys_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(64))
    role = db.Column(db.String(32), nullable=False, default=ROLE_OPERATOR)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    api_token_hash = db.Column(db.String(128))
    login_failed_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)

    def set_api_token(self, raw_token):
        self.api_token_hash = _hash_token(raw_token)

    def check_api_token(self, raw_token):
        if not raw_token or not self.api_token_hash:
            return False
        return hmac.compare_digest(self.api_token_hash, _hash_token(raw_token))

    @property
    def is_super_admin(self):
        return self.role == ROLE_SUPER_ADMIN

    @property
    def is_admin(self):
        return self.role in (ROLE_ADMIN, ROLE_SUPER_ADMIN)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    def has_perm(self, code):
        """模板/路由里判断功能权限（super_admin 恒为 True）。"""
        return user_has_permission(self, code)

    def to_dict(self, include_api_token_hint=False):
        data = {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name or self.username,
            "role": self.role,
            "role_label": self.role_label,
            "is_active": self.is_active,
            "must_change_password": self.must_change_password,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "last_login_at": self.last_login_at.strftime("%Y-%m-%d %H:%M") if self.last_login_at else "",
            "locked_until": self.locked_until.strftime("%Y-%m-%d %H:%M") if self.locked_until else "",
        }
        if include_api_token_hint:
            data["has_api_token"] = bool(self.api_token_hash)
        return data


def _hash_token(raw_token):
    return "sha256:" + hmac.new(
        raw_token.encode("utf-8"),
        digestmod="sha256",
    ).hexdigest()


def generate_api_token():
    return "hwt_" + secrets.token_urlsafe(32)


def is_locked(user):
    return bool(user.locked_until and user.locked_until > datetime.now())


def register_login_failure(user):
    user.login_failed_count = (user.login_failed_count or 0) + 1
    if user.login_failed_count >= MAX_LOGIN_FAILURES:
        user.locked_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
        user.login_failed_count = 0


class AuditLog(db.Model):
    __tablename__ = "sys_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True)
    action = db.Column(db.String(64), index=True)
    detail = db.Column(db.String(512))
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)


# ---------------------------------------------------------------------------
# 功能权限：可授权的系统功能点（页面 / API）
# super_admin 恒为全部权限；admin/operator 的权限存 sys_role_permission 表
# ---------------------------------------------------------------------------
FUNCTION_PERMISSIONS = {
    "ai_detection": "菌种检测",
    "strain_db": "菌种数据库",
    "analysis": "趋势分析",
    "strain_showcase": "知识库",
    "maldi_matching": "MALDI-TOF匹配",
    "api_access": "远程调用API",
}

# 除账户管理（仅管理员角色）外的默认全量授权
def default_role_permissions(include_maldi=False):
    codes = ["ai_detection", "strain_db", "analysis", "strain_showcase", "api_access"]
    if include_maldi:
        codes.append("maldi_matching")
    return codes


class RolePermission(db.Model):
    __tablename__ = "sys_role_permission"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(32), nullable=False, index=True)
    permission = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        db.UniqueConstraint("role", "permission", name="uq_role_permission"),
    )


def get_role_permissions(role):
    """返回某角色已授权的功能码集合。"""
    rows = RolePermission.query.filter_by(role=role).all()
    return {row.permission for row in rows}


def user_has_permission(user, code):
    """判断账号是否拥有某功能权限；super_admin 恒为 True。"""
    if not user or not user.is_active:
        return False
    if user.role == ROLE_SUPER_ADMIN:
        return True
    return code in get_role_permissions(user.role)


def set_role_permissions(role, codes):
    """整体替换某角色的功能权限集合。"""
    RolePermission.query.filter_by(role=role).delete()
    for code in codes:
        if code in FUNCTION_PERMISSIONS:
            db.session.add(RolePermission(role=role, permission=code))


def audit(action, detail="", username=None, ip=None):
    """写一条审计日志（登录、账号操作）。"""
    try:
        db.session.add(AuditLog(
            username=username,
            action=action,
            detail=(detail or "")[:512],
            ip=ip,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
