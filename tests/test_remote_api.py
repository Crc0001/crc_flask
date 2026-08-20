# -*- coding: utf-8 -*-
"""测试用例：/api/v1 远程调用接口（vendor 模式实跑，Token 鉴权 + 返回结构）。"""
import os

import pytest

from conftest import VENDOR_TOKEN, multipart_image

pytestmark = pytest.mark.skipif(
    os.environ.get("HWISHAI_APP_ROLE") == "client",
    reason="vendor 远程 API 用例在 vendor 模式运行",
)

AUTH = {"Authorization": f"Bearer {VENDOR_TOKEN}"}


class TestRecognizeApi:
    def test_no_token_401(self, client, tiny_image):
        resp = client.post("/api/v1/recognize", data=multipart_image(tiny_image))
        assert resp.status_code == 401

    def test_bad_token_401(self, client, tiny_image):
        resp = client.post(
            "/api/v1/recognize",
            data=multipart_image(tiny_image),
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_missing_file_message(self, client):
        resp = client.post("/api/v1/recognize", headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is False
        assert "请上传图片" in resp.get_json()["message"]

    def test_recognize_returns_top3_structure(self, client, tiny_image):
        """完整识别管线：Top3 结构 + 知识库ID + 可选结果图。"""
        resp = client.post(
            "/api/v1/recognize",
            data={**multipart_image(tiny_image), "with_result_image": "1"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["model"].startswith("HwishAI")
        assert 1 <= len(data["top3"]) <= 3
        for item in data["top3"]:
            assert item["rank"] >= 1
            assert item["species_name"]
            assert 0.0 <= item["confidence"] <= 1.0
            assert "knowledge_record_id" in item
            assert "recognition_model" in item
        assert data["result_image_base64"]
        assert isinstance(data["plate_crop"], dict)
        assert isinstance(data["image_selection"], dict)

    def test_recognize_writes_audit_log(self, app, client, tiny_image):
        from app.models.user import AuditLog
        client.post("/api/v1/recognize", data=multipart_image(tiny_image), headers=AUTH)
        with app.app_context():
            rows = AuditLog.query.filter_by(action="api_recognize").order_by(
                AuditLog.id.desc()).limit(1).all()
        assert rows
        assert "测试客户A" in rows[0].username


class TestKnowledgeApi:
    def test_search_no_token_401(self, client):
        assert client.get("/api/v1/knowledge/search").status_code == 401

    def test_search_returns_records(self, client):
        resp = client.get(
            "/api/v1/knowledge/search",
            query_string={"q": "Bacillus", "per_page": "3"},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["total"] > 0
        assert len(data["records"]) <= 3
        for rec in data["records"]:
            assert rec["record_id"] > 0
            assert rec["species_name"]

    def test_detail_returns_sections(self, client):
        resp = client.get(
            "/api/v1/knowledge/search",
            query_string={"q": "Bacillus", "per_page": "1"},
            headers=AUTH,
        )
        record_id = resp.get_json()["records"][0]["record_id"]

        resp = client.get(f"/api/v1/knowledge/{record_id}", headers=AUTH)
        assert resp.status_code == 200
        record = resp.get_json()["record"]
        assert record["record_id"] == record_id
        assert len(record["taxonomy"]) == 7
        assert len(record["data_sections"]) == 9

    def test_detail_missing_404(self, client):
        resp = client.get("/api/v1/knowledge/999999999", headers=AUTH)
        assert resp.status_code == 404
