# -*- coding: utf-8 -*-
"""pytest 共享夹具与测试配置。

运行方式（在项目根目录）：
    vendor 模式（默认）： .venv\\Scripts\\python.exe -m pytest tests -m "not client" -q
    client 模式：          $env:HWISHAI_APP_ROLE='client'; .venv\\Scripts\\python.exe -m pytest tests -m client -q
    全部（顺序跑两遍）：    tests\\run_all_tests.bat

测试说明：
- 集成测试直接连开发库 crc_ai；所有写操作使用一次性数据并在 teardown 清理。
- 识别类用例不校验具体菌种（准确率由 eval_strain_recognition.py 评测），只校验管线与返回结构。
"""
import io
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 必须在导入 app 之前设置
os.environ.setdefault("HWISHAI_APP_ROLE", "vendor")
os.environ.setdefault(
    "HWISHAI_VENDOR_TOKENS",
    json.dumps({"test-token-123": "测试客户A"}, ensure_ascii=False),
)
# client 测试默认不配置上游（代理应返回"未配置"错误）
os.environ.setdefault("HWISHAI_API_BASE_URL", "")
os.environ.setdefault("HWISHAI_API_TOKEN", "")
# 引导账号初始密码显式提供（安全策略：缺失时拒绝自动创建，见 app/__init__.py）
os.environ.setdefault("BOOTSTRAP_SUPERADMIN_PASSWORD", "TestBootstrap123")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "TestBootstrap123")

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.user import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_OPERATOR,
    User,
    default_role_permissions,
    set_role_permissions,
)

VENDOR_TOKEN = "test-token-123"
IS_VENDOR = os.environ["HWISHAI_APP_ROLE"] == "vendor"

MISSING_OR_WRONG = "用户名或密码错误"


def pytest_configure(config):
    config.addinivalue_line("markers", "client: 仅 client 模式运行的用例")


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture()
def client(app):
    """测试客户端：自动为所有 POST 注入会话 CSRF Token 头（对应后端 _csrf_protect）。

    需要测"无 token 被拒"的用例请自行 app.test_client() 构造裸客户端。
    """
    c = app.test_client()
    _orig_post = c.post

    def post(*args, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("X-CSRF-Token", _csrf_for(c))
        kwargs["headers"] = headers
        return _orig_post(*args, **kwargs)

    c.post = post
    return c


def _csrf_for(client_obj):
    """给测试客户端播种会话并返回 CSRF Token（挂在客户端实例上，避免 id() 复用串台）。"""
    token = getattr(client_obj, "_hwai_csrf", None)
    if token:
        return token
    client_obj.get("/login")
    with client_obj.session_transaction() as sess:
        token = sess.get("_csrf_token") or ""
    client_obj._hwai_csrf = token
    return token


@pytest.fixture()
def tiny_image():
    """内存生成的小图，识别用例与上传用例共用。"""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (96, 96), color=(235, 235, 235)).save(buf, format="JPEG")
    return buf.getvalue()


TEST_SUPER_USERNAME = "test_super"
TEST_SUPER_PASSWORD = "TestSuper123"


@pytest.fixture(scope="session")
def test_super_user(app):
    """专用测试超级管理员账号：测试只用它登录，绝不触碰真实的 hwishai 账号。

    返回 {"id": int, "username": str}（避免跨会话持有 ORM 对象）。
    """
    from app.models.user import ROLE_SUPER_ADMIN, User

    with app.app_context():
        user = User.query.filter_by(username=TEST_SUPER_USERNAME).first()
        if not user:
            user = User(username=TEST_SUPER_USERNAME, display_name="测试超级管理员",
                        role=ROLE_SUPER_ADMIN)
            db.session.add(user)
        user.set_password(TEST_SUPER_PASSWORD)
        user.is_active = True
        user.must_change_password = False
        user.login_failed_count = 0
        user.locked_until = None
        db.session.commit()
        return {"id": user.id, "username": user.username}


@pytest.fixture()
def super_client(client, test_super_user):
    """已登录专用测试超级管理员（test_super）的测试客户端。"""
    client.get("/logout")
    resp = client.post(
        "/login",
        data={"username": TEST_SUPER_USERNAME, "password": TEST_SUPER_PASSWORD},
    )
    assert resp.status_code == 302, "test_super 登录失败"
    return client


@pytest.fixture()
def temp_user(app):
    """创建一次性账号，用例结束自动删除。"""
    created_ids = []

    def _make(username, role=ROLE_OPERATOR, password="TestPass123", **kwargs):
        with app.app_context():
            user = User(username=username, role=role, **kwargs)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            created_ids.append(user.id)
        return user

    yield _make

    with app.app_context():
        for uid in created_ids:
            user = db.session.get(User, uid)
            if user:
                db.session.delete(user)
        db.session.commit()


@pytest.fixture()
def temp_admin(app, temp_user):
    """一次性管理员账号（避免依赖 admin 默认密码状态）。"""
    return temp_user("test_admin_tmp", role=ROLE_ADMIN, password="TestPass123")


@pytest.fixture()
def temp_operator(app, temp_user):
    """一次性操作员账号。"""
    return temp_user("test_op_tmp", role=ROLE_OPERATOR, password="TestPass123")


@pytest.fixture()
def restore_permissions(app):
    """权限用例结束恢复 admin/operator 默认权限。"""
    yield
    with app.app_context():
        include_maldi = IS_VENDOR
        set_role_permissions(ROLE_ADMIN, default_role_permissions(include_maldi=include_maldi))
        set_role_permissions(ROLE_OPERATOR, default_role_permissions(include_maldi=include_maldi))
        db.session.commit()


@pytest.fixture()
def temp_sample(app):
    """一次性样品记录，用例结束删除。"""
    from app.models.sample import Sample

    created_ids = []

    def _make(sample_code, **kwargs):
        with app.app_context():
            sample = Sample(sample_code=sample_code, **kwargs)
            db.session.add(sample)
            db.session.commit()
            created_ids.append(sample.id)
        return sample

    yield _make

    with app.app_context():
        for sid in created_ids:
            sample = db.session.get(Sample, sid)
            if sample:
                db.session.delete(sample)
        db.session.commit()


def login(client, username, password):
    client.get("/logout")
    return client.post("/login", data={"username": username, "password": password})


def multipart_image(image_bytes, filename="test.jpg"):
    return {
        "image": (io.BytesIO(image_bytes), filename),
        "content_type": "multipart/form-data",
        "buffered": True,
    }
