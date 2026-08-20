# -*- coding: utf-8 -*-
"""测试用例：账户管理接口（增删改查 / 启停 / 密码 / Token / 层级）。"""
import os

import pytest

from conftest import login

pytestmark = pytest.mark.skipif(
    os.environ.get("HWISHAI_APP_ROLE") == "client",
    reason="账户管理用例在 vendor 模式运行",
)


class TestUserCrud:
    def test_create_user(self, app, super_client, temp_user):
        resp = super_client.post(
            "/admin/accounts/create",
            data={"username": "test_crud_u", "display_name": "测试",
                  "role": "operator", "password": "TestPass123"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(username="test_crud_u").first()
            assert user is not None
            assert user.role == "operator"
            # 清理
            from app.extensions import db
            db.session.delete(user)
            db.session.commit()

    def test_duplicate_username_rejected(self, super_client, temp_operator):
        resp = super_client.post(
            "/admin/accounts/create",
            data={"username": temp_operator.username, "display_name": "x",
                  "role": "operator", "password": "TestPass123"},
        )
        assert resp.status_code == 400
        assert "已存在" in resp.get_json()["message"]

    def test_short_password_rejected(self, super_client):
        resp = super_client.post(
            "/admin/accounts/create",
            data={"username": "test_short_pwd", "role": "operator", "password": "123"},
        )
        assert resp.status_code == 400
        assert "8" in resp.get_json()["message"]

    def test_update_display_and_role(self, app, super_client, temp_operator):
        resp = super_client.post(
            f"/admin/accounts/{temp_operator.id}/update",
            data={"display_name": "改名后", "role": "operator", "is_active": "1"},
        )
        assert resp.status_code == 200
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(id=temp_operator.id).first()
            assert user.display_name == "改名后"

    def test_disable_user_blocks_login(self, app, client, super_client, temp_operator):
        resp = super_client.post(
            f"/admin/accounts/{temp_operator.id}/update",
            data={"display_name": "x", "role": "operator", "is_active": "0"},
        )
        assert resp.status_code == 200
        resp = login(client, temp_operator.username, "TestPass123")
        assert resp.status_code == 200
        # 统一文案，不暴露账号状态（防枚举）
        assert "用户名或密码错误" in resp.get_data(as_text=True)

    def test_delete_user(self, app, super_client, temp_user):
        user = temp_user("test_del_u")
        resp = super_client.post(f"/admin/accounts/{user.id}/delete")
        assert resp.status_code == 200
        with app.app_context():
            from app.models.user import User
            assert User.query.filter_by(id=user.id).first() is None

    def test_cannot_delete_self(self, super_client, test_super_user):
        """超级管理员自身受保护（连自己也不能删除），返回 403。"""
        resp = super_client.post(f"/admin/accounts/{test_super_user['id']}/delete")
        assert resp.status_code == 403
        assert "超级管理员" in resp.get_json()["message"]

    def test_cannot_disable_self(self, super_client, test_super_user):
        """超级管理员不能通过管理页停用自己。"""
        resp = super_client.post(
            f"/admin/accounts/{test_super_user['id']}/update",
            data={"display_name": "x", "role": "super_admin", "is_active": "0"},
        )
        assert resp.status_code == 403

    def test_superadmin_protected_from_others(self, client, temp_admin, test_super_user):
        login(client, temp_admin.username, "TestPass123")
        resp = client.post(f"/admin/accounts/{test_super_user['id']}/reset_password",
                           data={"password": "TestPass123"})
        assert resp.status_code == 403


class TestResetPassword:
    def test_reset_password_and_force_change(self, client, super_client, temp_operator):
        resp = super_client.post(
            f"/admin/accounts/{temp_operator.id}/reset_password",
            data={"password": "ResetPass123", "force_change": "1"},
        )
        assert resp.status_code == 200

        resp = login(client, temp_operator.username, "ResetPass123")
        assert resp.status_code == 302
        assert "/change_password" in resp.headers["Location"]


class TestApiToken:
    def test_reset_token_returns_once(self, app, super_client, temp_operator):
        resp = super_client.post(f"/admin/accounts/{temp_operator.id}/reset_token")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["token"].startswith("hwt_")

        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(id=temp_operator.id).first()
            assert user.api_token_hash
            assert user.check_api_token(data["token"])
            assert not user.check_api_token("hwt_forged_token")

    def test_operator_cannot_manage_tokens(self, client, temp_operator):
        login(client, temp_operator.username, "TestPass123")
        resp = client.post(f"/admin/accounts/{temp_operator.id}/reset_token")
        assert resp.status_code == 403
