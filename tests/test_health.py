# -*- coding: utf-8 -*-
"""测试用例：健康检查接口 /healthz（公开，无登录要求）。"""
import os

import pytest


class TestHealthzVendor:
    pytestmark = pytest.mark.skipif(
        os.environ.get("HWISHAI_APP_ROLE") == "client", reason="vendor 用例"
    )

    def test_healthz_public_and_ok(self, client):
        # 无需登录会话即可访问（页面状态指示与云中继探活用）
        resp = client.get("/healthz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["status"] == "ok"
        assert data["role"] == "vendor"
        assert data["version"]


class TestHealthzClient:
    pytestmark = pytest.mark.client
    _skip_vendor = pytest.mark.skipif(
        os.environ.get("HWISHAI_APP_ROLE") != "client", reason="client 用例"
    )

    @_skip_vendor
    def test_healthz_public(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200

    @_skip_vendor
    def test_healthz_degraded_when_unconfigured(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "client"
        assert data["success"] is True
        assert data["status"] == "degraded"
        assert data["upstream_ok"] is False
        assert "未配置" in data["upstream_message"]
