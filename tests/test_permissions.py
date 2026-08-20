# -*- coding: utf-8 -*-
"""测试用例：功能权限（页面 403 / 菜单隐藏 / API 403 / 保存生效）。"""
import os

import pytest

from conftest import login

pytestmark = pytest.mark.skipif(
    os.environ.get("HWISHAI_APP_ROLE") == "client",
    reason="权限页面用例在 vendor 模式运行",
)


class TestAdminConsoleAccess:
    def test_superadmin_sees_console(self, super_client):
        for path in ("/admin/", "/admin/accounts", "/admin/permissions", "/admin/logs"):
            assert super_client.get(path).status_code == 200

    def test_operator_blocked_from_console(self, client, temp_operator):
        login(client, temp_operator.username, "TestPass123")
        assert client.get("/admin/").status_code == 403
        assert client.get("/admin/accounts").status_code == 403
        assert client.get("/admin/permissions").status_code == 403
        assert client.get("/admin/logs").status_code == 403

    def test_anon_console_redirects_to_login(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestPermissionEnforcement:
    def test_revoke_function_permission(self, app, client, super_client, temp_operator,
                                        restore_permissions):
        """操作员只保留菌种数据库：其它页面/接口全部 403，菜单同步隐藏。"""
        from app.extensions import db
        from app.models.user import set_role_permissions

        with app.app_context():
            set_role_permissions("operator", ["strain_db"])
            db.session.commit()

        login(client, temp_operator.username, "TestPass123")

        assert client.get("/strain_db/").status_code == 200
        assert client.get("/ai_detection").status_code == 403
        assert client.get("/strain_showcase/").status_code == 403
        assert client.get("/analysis/").status_code == 403

        html = client.get("/strain_db/").get_data(as_text=True)
        assert 'href="/ai_detection"' not in html
        assert 'href="/strain_db"' in html

        resp = client.post("/api/orb_detect", data={"image": "bad"})
        assert resp.status_code == 403
        assert resp.get_json()["message"] == "无权限访问该功能"

    def test_permissions_save_takes_effect(self, app, client, super_client, temp_operator,
                                           restore_permissions):
        from app.extensions import db
        from app.models.user import ROLE_OPERATOR, RolePermission

        resp = super_client.post(
            "/admin/permissions/save",
            data={"perm_operator": ["strain_showcase"], "perm_admin": []},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        with app.app_context():
            granted = {r.permission for r in RolePermission.query.filter_by(role=ROLE_OPERATOR)}
        assert granted == {"strain_showcase"}

        login(client, temp_operator.username, "TestPass123")
        assert client.get("/strain_showcase/").status_code == 200
        assert client.get("/strain_db/").status_code == 403


class TestAdminRoleHierarchy:
    def test_admin_cannot_create_admin(self, client, temp_admin):
        login(client, temp_admin.username, "TestPass123")
        resp = client.post(
            "/admin/accounts/create",
            data={"username": "tmp_admin_x", "display_name": "x",
                  "role": "admin", "password": "TestPass123"},
        )
        assert resp.status_code == 403

    def test_admin_cannot_see_or_touch_superadmin(self, client, temp_admin, test_super_user):
        login(client, temp_admin.username, "TestPass123")
        html = client.get("/admin/accounts").get_data(as_text=True)
        assert test_super_user["username"] not in html
        assert "hwishai" not in html

        resp = client.post(f"/admin/accounts/{test_super_user['id']}/update",
                           data={"display_name": "hack", "role": "operator"})
        assert resp.status_code == 403

    def test_admin_can_manage_operator(self, client, temp_admin, temp_operator):
        login(client, temp_admin.username, "TestPass123")
        resp = client.post(
            f"/admin/accounts/{temp_operator.id}/reset_password",
            data={"password": "NewPass12345", "force_change": "1"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
