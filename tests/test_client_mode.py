# -*- coding: utf-8 -*-
"""测试用例：client 模式（依赖隔离 / 代理行为 / Token 门禁）。

运行方式：先设置 HWISHAI_APP_ROLE=client 再跑 pytest（见 tests/run_all_tests.bat）。
"""
import os
import sys

import pytest

pytestmark = pytest.mark.client

if os.environ.get("HWISHAI_APP_ROLE") != "client":
    pytest.skip("client 模式用例需 HWISHAI_APP_ROLE=client 运行", allow_module_level=True)

from conftest import login, multipart_image  # noqa: E402


class TestDependencyIsolation:
    def test_no_torch_imported(self):
        assert "torch" not in sys.modules
        assert "ultralytics" not in sys.modules
        assert "cv2" not in sys.modules
        assert "open_clip" not in sys.modules

    def test_no_maldi_route(self, app):
        assert not any("maldi_matching" in rule.rule for rule in app.url_map.iter_rules())

    def test_vendor_only_permission_hidden(self):
        """client 模式不提供 MALDI 权限：默认种子与权限管理页都不含该权限码。"""
        from app.models.user import default_role_permissions
        from app.routes.admin_console import _visible_permissions

        codes = default_role_permissions(include_maldi=False)
        assert "maldi_matching" not in codes
        visible = [code for code, _ in _visible_permissions()]
        assert "maldi_matching" not in visible


class TestClientProxies:
    def test_login_and_page(self, client, temp_operator):
        resp = login(client, temp_operator.username, "TestPass123")
        assert resp.status_code == 302
        assert client.get("/ai_detection").status_code == 200

    def test_orb_detect_unconfigured_error(self, client, temp_operator, tiny_image):
        """未配置我方服务地址时，识别代理返回明确错误。"""
        login(client, temp_operator.username, "TestPass123")
        resp = client.post("/api/orb_detect", data=multipart_image(tiny_image))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False
        assert "模型服务" in data["message"]

    def test_knowledge_page_unconfigured_error(self, client, temp_operator):
        login(client, temp_operator.username, "TestPass123")
        resp = client.get("/strain_showcase/")
        assert resp.status_code == 200
        assert "知识库服务暂时不可用" in resp.get_data(as_text=True)

    def test_operator_has_no_admin_menu(self, client, temp_operator):
        login(client, temp_operator.username, "TestPass123")
        html = client.get("/ai_detection").get_data(as_text=True)
        assert "管理控制台" not in html
        assert client.get("/admin/").status_code == 403

    def test_detection_page_hides_maldi_panels(self, client, temp_operator):
        """client 模式不提供 MALDI/16S 匹配（参考谱库在我方本地）。"""
        login(client, temp_operator.username, "TestPass123")
        html = client.get("/ai_detection").get_data(as_text=True)
        assert "MALDI-TOF质谱图" not in html
        assert "16S RNA序列" not in html


class TestApiTokenGate:
    def test_api_v1_requires_token(self, client):
        assert client.get("/api/v1/knowledge/search").status_code == 401

    def test_api_access_permission_gate(self, app, client, temp_operator, restore_permissions):
        """无 api_access 权限的账号 Token 被 403；授权后放行（未配置上游则 502）。"""
        from app.extensions import db
        from app.models.user import RolePermission, generate_api_token, set_role_permissions

        with app.app_context():
            set_role_permissions("operator", ["ai_detection"])
            user = temp_operator
            user = db.session.get(type(user), user.id)
            token = generate_api_token()
            user.set_api_token(token)
            db.session.commit()

        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/knowledge/search", headers=headers)
        assert resp.status_code == 403
        assert "未授权远程调用API" in resp.get_json()["message"]

        with app.app_context():
            set_role_permissions("operator", ["ai_detection", "api_access"])
            db.session.commit()

        resp = client.get("/api/v1/knowledge/search", query_string={"q": "x"}, headers=headers)
        assert resp.status_code == 502  # 未配置上游，转发失败
        assert "服务端未配置我方服务地址" in resp.get_json()["message"]

        with app.app_context():
            rows = RolePermission.query.filter_by(role="operator").all()
            assert any(r.permission == "api_access" for r in rows)
