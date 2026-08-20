# -*- coding: utf-8 -*-
"""测试用例：功能1 检测流程 + 报告录入/导出 + 功能2 菌种数据库 + 功能3 趋势分析。"""
import os

import pytest

from conftest import multipart_image

pytestmark = pytest.mark.skipif(
    os.environ.get("HWISHAI_APP_ROLE") == "client",
    reason="本地检测流程用例在 vendor 模式运行",
)

SAMPLE_CODE = "TESTCASE_FLOW_001"


@pytest.fixture()
def cleanup_report_sample(app):
    """报告流程用例结束删除测试样品。"""
    yield
    from app.extensions import db
    from app.models.sample import Sample
    with app.app_context():
        sample = Sample.query.filter_by(sample_code=SAMPLE_CODE).first()
        if sample:
            db.session.delete(sample)
            db.session.commit()


class TestOrbDetectWeb:
    def test_invalid_file_rejected(self, super_client):
        resp = super_client.post(
            "/api/orb_detect",
            data={"image": (__import__("io").BytesIO(b"not-an-image"), "bad.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is False

    def test_detect_returns_candidates(self, super_client, tiny_image):
        """上传真实图片走完整识别管线，返回网页所需全部字段。"""
        resp = super_client.post("/api/orb_detect", data=multipart_image(tiny_image))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["accepted"] is True
        assert 1 <= len(data["candidates"]) <= 3
        first = data["candidates"][0]
        for key in ("rank", "matched_strain_name", "classifier_species_name",
                    "classifier_confidence", "effective_confidence", "match_score",
                    "recognition_model"):
            assert key in first
        assert data["result_image_url"].startswith("/static/results/")
        assert "plate_crop" in data and "image_selection" in data

    def test_detect_writes_detect_submit_log(self, app, super_client, tiny_image):
        from app.models.user import AuditLog
        super_client.post("/api/orb_detect", data=multipart_image(tiny_image))
        with app.app_context():
            rows = AuditLog.query.filter_by(action="detect_submit").order_by(
                AuditLog.id.desc()).limit(1).all()
        assert rows
        assert "Top1=" in rows[0].detail


class TestReportFlow:
    def test_report_create_check_update(self, app, super_client, cleanup_report_sample):
        resp = super_client.post(
            "/api/save_detection_report",
            data={"sample_code": SAMPLE_CODE, "collect_date": "2026-01-15",
                  "source_location": "测试地点", "strain_name": "测试菌种"},
        )
        assert resp.get_json()["success"] is True
        assert resp.get_json()["action"] == "created"

        resp = super_client.get(
            "/api/check_sample_code", query_string={"sample_code": SAMPLE_CODE}
        )
        data = resp.get_json()
        assert data["exists"] is True
        assert data["existing"]["strain_name"] == "测试菌种"

        resp = super_client.post(
            "/api/save_detection_report",
            data={"sample_code": SAMPLE_CODE, "collect_date": "2026-01-16",
                  "source_location": "测试地点", "strain_name": "更新菌种"},
        )
        assert resp.get_json()["success"] is True
        assert resp.get_json()["action"] == "updated"

    def test_report_missing_code_rejected(self, super_client):
        resp = super_client.post(
            "/api/save_detection_report",
            data={"sample_code": "", "strain_name": "x"},
        )
        assert resp.get_json()["success"] is False

    def test_export_pdf(self, super_client, tiny_image, cleanup_report_sample):
        from app.services.report_pdf import _get_pdf_chinese_font_name
        if not _get_pdf_chinese_font_name():
            pytest.skip("本机无中文字体，跳过 PDF 用例")
        # 先保证样品存在
        super_client.post(
            "/api/save_detection_report",
            data={"sample_code": SAMPLE_CODE, "collect_date": "2026-01-15",
                  "source_location": "测试地点", "strain_name": "测试菌种"},
        )

        resp = super_client.post(
            "/api/export_detection_report_pdf",
            data={
                "sample_code": SAMPLE_CODE,
                "collect_date": "2026-01-15",
                "source_location": "测试地点",
                "strain_name": "测试菌种",
                "detection_result": "测试结论",
                "image": (__import__("io").BytesIO(tiny_image), "test.jpg"),
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/pdf"
        assert resp.data[:4] == b"%PDF"

    def test_report_audit_logged(self, app, super_client, cleanup_report_sample):
        super_client.post(
            "/api/save_detection_report",
            data={"sample_code": SAMPLE_CODE, "collect_date": "2026-01-15",
                  "source_location": "测试地点", "strain_name": "测试菌种"},
        )
        from app.models.user import AuditLog
        with app.app_context():
            rows = AuditLog.query.filter_by(action="report_save").order_by(
                AuditLog.id.desc()).limit(1).all()
        assert rows
        assert SAMPLE_CODE in rows[0].detail


class TestStrainDb:
    def test_list_page(self, super_client):
        resp = super_client.get("/strain_db/")
        assert resp.status_code == 200

    def test_edit_sample(self, app, super_client, temp_sample):
        sample = temp_sample("TESTCASE_EDIT", collect_location="地点A")
        resp = super_client.post(
            f"/strain_db/edit/{sample.id}",
            data={"sample_code": sample.sample_code, "collector": "张三",
                  "collect_location": "地点B"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert resp.get_json()["data"]["collect_location"] == "地点B"

    def test_delete_sample(self, app, super_client, temp_sample):
        sample = temp_sample("TESTCASE_DEL")
        resp = super_client.post(f"/strain_db/delete/{sample.id}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


class TestMaldiModule:
    """独立 MALDI 页面已移除；匹配接口与检测页内嵌面板保留（仅 vendor）。"""

    def test_standalone_page_removed(self, super_client):
        assert super_client.get("/maldi_matching").status_code == 404

    def test_match_apis_still_exist(self, app):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        assert "/api/maldi/match" in rules
        assert "/api/16s/match" in rules

    def test_detection_page_contains_maldi_panels(self, super_client):
        html = super_client.get("/ai_detection").get_data(as_text=True)
        assert "MALDI-TOF质谱图" in html
        assert "16S RNA序列" in html

    def test_sidebar_has_no_maldi_link(self, super_client):
        html = super_client.get("/ai_detection").get_data(as_text=True)
        assert 'href="/maldi_matching"' not in html


class TestAnalysis:
    def test_analysis_page(self, super_client):
        assert super_client.get("/analysis/").status_code == 200

    def test_analysis_data(self, super_client):
        resp = super_client.get("/analysis/data",
                                  query_string={"type": "strain", "granularity": "day"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "labels" in data
        assert "datasets" in data
