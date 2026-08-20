# -*- coding: utf-8 -*-
"""P0 安全修复回归测试（对应《首轮源代码调研报告》V-01/V-03/V-04/V-07/L-08）。

覆盖：
- 上传校验（扩展名白名单 + 魔数 + 像素上限 + 服务端安全文件名）；
- .html 伪装 image/* 上传被拒绝、不会落盘 static/uploads（存储型 XSS 根因）；
- /api/v1/recognize 同样拒绝可疑上传且拒绝前不跑识别管线；
- 全站安全响应头；
- 请求体超限返回 413 JSON；
- admin 停用/启用不再把角色静默降级为 operator（V-07）；
- 引导账号复活标记（instance/.bootstrap_done）已生成。
"""
import io
import os
import struct
import zlib

import pytest


def _png_with_dims(width, height):
    """构造最小合法 PNG 头（仅 IHDR，不完整数据），用于像素上限测试。"""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    crc = zlib.crc32(chunk) & 0xFFFFFFFF
    return sig + struct.pack(">I", len(ihdr)) + chunk + struct.pack(">I", crc)


class TestUploadGuard:
    def test_valid_jpg_passes_and_gets_safe_name(self, tiny_image):
        from app.services.upload_guard import validate_image_upload

        ok, message, safe_name = validate_image_upload("菌落.jpg", tiny_image)
        assert ok, message
        assert safe_name.startswith("upload_") and safe_name.endswith(".jpg")

    def test_html_with_image_mime_rejected(self):
        from app.services.upload_guard import validate_image_upload

        ok, message, _ = validate_image_upload(
            "evil.html", b"<html><script>alert(1)</script></html>"
        )
        assert not ok
        assert "不支持的图片格式" in message

    def test_extension_magic_mismatch_rejected(self, tiny_image):
        from app.services.upload_guard import validate_image_upload

        # JPEG 内容套 .png 扩展名 → 拒绝
        ok, message, _ = validate_image_upload("fake.png", tiny_image)
        assert not ok
        assert "不符" in message

    def test_pixel_bomb_rejected(self):
        from app.services.upload_guard import validate_image_upload

        data = _png_with_dims(120000, 120000)  # 144 亿像素
        ok, message, _ = validate_image_upload("bomb.png", data)
        assert not ok
        assert "尺寸过大" in message

    def test_oversize_bytes_rejected(self):
        from app.services.upload_guard import (
            MAX_IMAGE_BYTES,
            validate_image_upload,
        )

        ok, message, _ = validate_image_upload("big.jpg", b"\xff\xd8\xff" + b"0" * (MAX_IMAGE_BYTES + 1))
        assert not ok
        assert "过大" in message


class TestDetectUploadHardening:
    def test_detect_rejects_html_and_does_not_store(self, app, super_client):
        resp = super_client.post(
            "/api/orb_detect",
            data={
                "image": (
                    io.BytesIO(b"<html><script>alert(1)</script></html>"),
                    "evil.html",
                    "image/png",
                )
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is False

        upload_dir = os.path.join(app.root_path, "static", "uploads")
        leaked = [f for f in os.listdir(upload_dir) if "evil" in f]
        assert not leaked, f"可疑文件落盘了 static/uploads: {leaked}"

    def test_detect_rejects_magic_mismatch(self, super_client, tiny_image):
        resp = super_client.post(
            "/api/orb_detect",
            data={"image": (io.BytesIO(tiny_image), "fake.png", "image/png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is False

    def test_remote_api_recognize_rejects_html(self, app, client):
        resp = client.post(
            "/api/v1/recognize",
            headers={"Authorization": "Bearer test-token-123"},
            data={
                "image": (
                    io.BytesIO(b"<script>alert(1)</script>"),
                    "evil.html",
                    "image/png",
                )
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is False
        assert "不支持" in payload["message"] or "不符" in payload["message"]


class TestSecurityHeaders:
    def test_headers_present(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "default-src" in resp.headers.get("Content-Security-Policy", "")

    def test_413_returns_json_for_api(self, app, super_client):
        app.config["MAX_CONTENT_LENGTH"] = 1024
        try:
            resp = super_client.post(
                "/api/orb_detect",
                data={
                    "image": (io.BytesIO(b"\xff\xd8\xff" + b"0" * 4096),
                              "big.jpg", "image/jpeg")
                },
                content_type="multipart/form-data",
            )
        finally:
            app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
        assert resp.status_code == 413
        assert resp.get_json()["success"] is False


class TestAdminToggleKeepsRole:
    def test_toggle_active_does_not_demote_admin(self, app, super_client, temp_admin):
        resp = super_client.post(
            f"/admin/accounts/{temp_admin.id}/update",
            data={"is_active": "0"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        from app.extensions import db
        from app.models.user import User

        with app.app_context():
            target = db.session.get(User, temp_admin.id)
            assert target.role == "admin", "停用操作把 admin 静默降级了"
            assert target.is_active is False


class TestBootstrapMarker:
    def test_marker_written(self, app):
        marker = os.path.join(app.instance_path, ".bootstrap_done")
        assert os.path.exists(marker)
