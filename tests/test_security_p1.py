# -*- coding: utf-8 -*-
"""P1 安全加固回归测试（对应《首轮源代码调研报告》P1 批次）。

覆盖：CSRF、must_change_password 全局拦截、开放重定向反斜杠、锁定不续期与重置解锁、
登录失败限流、API 令牌仅 Bearer + 端点 scope、16S 长度上限、MALDI 参考谱管理员权限、
错误信息不泄露内部细节。
"""
import io

from conftest import login, multipart_image


class TestCsrf:
    def test_post_without_token_rejected(self, app, temp_operator):
        # 裸客户端：不注入 CSRF 头，也不带表单 token
        raw = app.test_client()
        resp = raw.post(
            "/login",
            data={"username": temp_operator.username, "password": "TestPass123"},
        )
        assert resp.status_code == 403

    def test_post_with_form_token_ok(self, app, temp_operator):
        raw = app.test_client()
        raw.get("/login")
        with raw.session_transaction() as sess:
            token = sess.get("_csrf_token")
        resp = raw.post(
            "/login",
            data={
                "username": temp_operator.username,
                "password": "TestPass123",
                "csrf_token": token,
            },
        )
        assert resp.status_code == 302

    def test_admin_api_without_token_rejected(self, app, temp_admin):
        raw = app.test_client()
        raw.get("/login")
        with raw.session_transaction() as sess:
            token = sess["_csrf_token"]
        raw.post("/login", data={
            "username": temp_admin.username, "password": "TestPass123",
            "csrf_token": token,
        })
        resp = raw.post(f"/admin/accounts/{temp_admin.id}/reset_token")
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False


class TestMustChangePassword:
    def test_global_block_and_page(self, client, temp_user):
        user = temp_user("test_p1_must_change", must_change_password=True)
        login(client, user.username, "TestPass123")

        resp = client.get("/strain_db/")
        assert resp.status_code == 302
        assert "/change_password" in resp.headers["Location"]

        resp = client.get("/api/check_sample_code", query_string={"sample_code": "X"})
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False

        page = client.get("/change_password")
        assert page.status_code == 200
        # 强制改密期间不显示"暂不修改"跳过链接
        assert "暂不修改" not in page.get_data(as_text=True)


class TestOpenRedirect:
    def test_backslash_bypass_blocked(self):
        from app.routes.auth import _safe_next

        assert _safe_next("/\\evil.com") is None
        assert _safe_next("//evil.com") is None
        assert _safe_next("https://evil.com") is None
        assert _safe_next("/strain_db/?x=1") == "/strain_db/?x=1"
        assert _safe_next("relative") == "/"


class TestLockoutHardening:
    def test_locked_until_not_extended_by_more_failures(self, app, client, temp_user):
        from app.extensions import db
        from app.models.user import User

        user = temp_user("test_p1_lockout")
        for _ in range(5):
            client.post("/login", data={"username": user.username, "password": "WrongPass999"})

        with app.app_context():
            locked = db.session.get(User, user.id)
            first_locked_until = locked.locked_until
            assert first_locked_until is not None

        # 锁定期间继续提交错误密码：不应延长 locked_until（防无限续锁）
        for _ in range(5):
            client.post("/login", data={"username": user.username, "password": "WrongPass999"})

        with app.app_context():
            locked = db.session.get(User, user.id)
            assert locked.locked_until == first_locked_until

    def test_reset_password_clears_lock(self, app, client, temp_user):
        from app.extensions import db
        from app.models.user import User
        from conftest import TEST_SUPER_PASSWORD

        user = temp_user("test_p1_reset_lock")
        for _ in range(5):
            client.post("/login", data={"username": user.username, "password": "WrongPass999"})

        with app.app_context():
            assert db.session.get(User, user.id).locked_until is not None

        # 用测试超级管理员登录后执行重置（避免与 client 共用登录态）
        login(client, "test_super", TEST_SUPER_PASSWORD)
        resp = client.post(
            f"/admin/accounts/{user.id}/reset_password",
            data={"password": "ResetPass123", "force_change": "1"},
        )
        assert resp.status_code == 200

        with app.app_context():
            target = db.session.get(User, user.id)
            assert target.locked_until is None
            assert target.login_failed_count == 0


class TestLoginRateLimit:
    def test_fail_rate_limit_per_user(self, app, client, temp_user):
        user = temp_user("test_p1_rate")
        app.config["LOGIN_RATE_FAIL_PER_USER"] = (3, 300)
        try:
            for _ in range(3):
                resp = client.post(
                    "/login", data={"username": user.username, "password": "WrongPass999"}
                )
                assert "用户名或密码错误" in resp.get_data(as_text=True)
            resp = client.post(
                "/login", data={"username": user.username, "password": "WrongPass999"}
            )
            assert "稍后再试" in resp.get_data(as_text=True)
        finally:
            app.config["LOGIN_RATE_FAIL_PER_USER"] = (60, 300)


class TestApiTokenHardening:
    def test_query_string_token_rejected(self, client):
        resp = client.get("/api/v1/knowledge/search", query_string={"token": "test-token-123"})
        assert resp.status_code == 401

    def test_scoped_token_denies_recognize(self, app, client, tiny_image):
        app.config["VENDOR_API_TOKENS"] = {
            "scoped-token": {"name": "受限客户", "scopes": ["knowledge_search"]},
        }
        try:
            headers = {"Authorization": "Bearer scoped-token"}
            resp = client.post(
                "/api/v1/recognize",
                headers=headers,
                data=multipart_image(tiny_image),
            )
            assert resp.status_code == 403

            resp = client.get("/api/v1/knowledge/search", headers=headers)
            assert resp.status_code == 200
        finally:
            app.config["VENDOR_API_TOKENS"] = {"test-token-123": "测试客户A"}

    def test_unscoped_token_full_access(self, app, client):
        # 兼容旧格式：纯字符串客户名 = 全端点权限
        app.config["VENDOR_API_TOKENS"] = {"legacy-token": "老客户"}
        try:
            resp = client.get(
                "/api/v1/knowledge/search",
                headers={"Authorization": "Bearer legacy-token"},
            )
            assert resp.status_code == 200
        finally:
            app.config["VENDOR_API_TOKENS"] = {"test-token-123": "测试客户A"}


class TestMaldiHardening:
    def test_16s_overlong_rejected(self, super_client):
        sequence = "A" * 2100
        resp = super_client.post(
            "/api/16s/match",
            data={"sequence": sequence},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is False
        assert "过长" in payload["message"]

    def test_reference_admin_only(self, app, client, temp_operator):
        login(client, temp_operator.username, "TestPass123")

        resp = client.post(
            "/api/maldi/reference/add",
            data={
                "file": (io.BytesIO(b"m/z\tintensity\n1.0\t100\n"), "ref.txt"),
                "strain_id": "1",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 403
        assert "仅限管理员" in resp.get_json()["message"]

        resp = client.delete("/api/maldi/reference/1")
        assert resp.status_code == 403
        assert "仅限管理员" in resp.get_json()["message"]


class TestErrorMessages:
    def test_no_internal_detail_in_upload_error(self, super_client, tiny_image):
        # 扩展名与魔数不符 → 只返回校验文案，不泄露内部异常
        resp = super_client.post(
            "/api/orb_detect",
            data={"image": (io.BytesIO(tiny_image), "fake.png", "image/png")},
            content_type="multipart/form-data",
        )
        message = resp.get_json()["message"]
        assert "Traceback" not in message
        assert "不符" in message


class TestCookieConfig:
    def test_secure_flag_default_off_for_intranet_http(self):
        from app.config import Config

        # 内网 HTTP 明文部署下 Secure 必须为 False，否则会话 Cookie 无法传输
        assert Config.SESSION_COOKIE_SECURE is False
