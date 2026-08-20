# -*- coding: utf-8 -*-
"""测试用例：登录 / 登出 / 会话拦截 / 改密 / 锁定。"""
from conftest import login


class TestSessionGate:
    """未登录时的全局拦截。"""

    def test_anon_page_redirects_to_login(self, client):
        resp = client.get("/ai_detection")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_anon_business_api_returns_401(self, client):
        resp = client.get("/api/check_sample_code", query_string={"sample_code": "X"})
        assert resp.status_code == 401
        assert resp.get_json()["success"] is False

    def test_anon_api_v1_returns_401(self, client):
        resp = client.get("/api/v1/knowledge/search")
        assert resp.status_code == 401

    def test_login_page_ok(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "login-card" in resp.get_data(as_text=True)

    def test_next_redirect_works(self, client, temp_operator):
        client.get("/logout")
        resp = client.get("/login", query_string={"next": "/strain_db/"})
        assert resp.status_code == 200
        # 表单 action 会携带 next 参数（真实浏览器流程）
        resp = client.post(
            "/login?next=/strain_db/",
            data={"username": temp_operator.username, "password": "TestPass123"},
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/strain_db/")

    def test_open_redirect_blocked(self, client, temp_operator):
        client.get("/logout")
        resp = client.get("/login", query_string={"next": "//evil.com"})
        assert resp.status_code == 200
        resp = client.post(
            "/login", data={"username": temp_operator.username, "password": "TestPass123"}
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("/")
        assert "evil.com" not in resp.headers["Location"]


class TestLoginLogout:
    def test_wrong_password_shows_error(self, client, temp_user):
        user = temp_user("test_wrong_pwd")
        resp = client.post("/login", data={"username": user.username, "password": "BadPass999"})
        assert resp.status_code == 200
        assert "用户名或密码错误" in resp.get_data(as_text=True)

    def test_unknown_user_shows_error(self, client):
        resp = client.post("/login", data={"username": "no_such_user_x", "password": "x" * 9})
        assert resp.status_code == 200
        assert "用户名或密码错误" in resp.get_data(as_text=True)

    def test_login_success_and_page_access(self, client, temp_operator):
        resp = login(client, temp_operator.username, "TestPass123")
        assert resp.status_code == 302
        assert client.get("/ai_detection").status_code == 200

    def test_logout_clears_session(self, client, temp_operator):
        login(client, temp_operator.username, "TestPass123")
        assert client.get("/ai_detection").status_code == 200
        resp = client.get("/logout")
        assert resp.status_code == 302
        assert client.get("/ai_detection").status_code == 302

    def test_lockout_after_five_failures(self, client, temp_user):
        user = temp_user("test_lockout")
        for _ in range(5):
            resp = client.post(
                "/login", data={"username": user.username, "password": "WrongPass999"}
            )
            assert resp.status_code == 200
        # 第 6 次即使密码正确也应被锁定
        resp = client.post("/login", data={"username": user.username, "password": "TestPass123"})
        assert resp.status_code == 200
        assert "锁定" in resp.get_data(as_text=True)

    def test_disabled_user_cannot_login(self, client, temp_user):
        user = temp_user("test_disabled", is_active=False)
        resp = client.post("/login", data={"username": user.username, "password": "TestPass123"})
        assert resp.status_code == 200
        # 统一文案，不暴露账号状态（防枚举）
        assert "用户名或密码错误" in resp.get_data(as_text=True)


class TestChangePassword:
    def test_must_change_flow(self, client, temp_user):
        user = temp_user("test_must_change", must_change_password=True)
        resp = login(client, user.username, "TestPass123")
        assert resp.status_code == 302
        assert "/change_password" in resp.headers["Location"]

        resp = client.get("/change_password")
        assert resp.status_code == 200

        resp = client.post(
            "/change_password",
            data={
                "old_password": "TestPass123",
                "new_password": "NewPass12345",
                "confirm_password": "NewPass12345",
            },
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")

        # 新密码可登录，旧密码失效
        client.get("/logout")
        resp = client.post("/login", data={"username": user.username, "password": "TestPass123"})
        assert resp.status_code == 200
        resp = client.post("/login", data={"username": user.username, "password": "NewPass12345"})
        assert resp.status_code == 302

    def test_change_password_validation(self, client, temp_user):
        user = temp_user("test_pwd_val")
        login(client, user.username, "TestPass123")

        # 旧密码错误
        resp = client.post(
            "/change_password",
            data={"old_password": "WrongOld1", "new_password": "NewPass12345",
                  "confirm_password": "NewPass12345"},
        )
        assert "当前密码不正确" in resp.get_data(as_text=True)

        # 新密码过短
        resp = client.post(
            "/change_password",
            data={"old_password": "TestPass123", "new_password": "short",
                  "confirm_password": "short"},
        )
        assert "至少 8 位" in resp.get_data(as_text=True)

        # 两次不一致
        resp = client.post(
            "/change_password",
            data={"old_password": "TestPass123", "new_password": "NewPass12345",
                  "confirm_password": "NewPass54321"},
        )
        assert "不一致" in resp.get_data(as_text=True)
