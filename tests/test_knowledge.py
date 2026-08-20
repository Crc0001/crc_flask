# -*- coding: utf-8 -*-
"""测试用例：功能4 知识库（vendor 本地页面 + 检索/详情）。"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HWISHAI_APP_ROLE") == "client",
    reason="vendor 知识库页面用例在 vendor 模式运行",
)


class TestShowcasePages:
    def test_index_page(self, super_client):
        resp = super_client.get("/strain_showcase/")
        assert resp.status_code == 200
        assert "菌种知识库" in resp.get_data(as_text=True)

    def test_search_renders_results(self, super_client):
        resp = super_client.get("/strain_showcase/",
                                  query_string={"q": "Bacillus"})
        assert resp.status_code == 200
        assert "Bacillus" in resp.get_data(as_text=True)

    def test_search_by_number(self, app, super_client):
        """按 BacDive 编号检索。"""
        from app.models import BacdiveRecord
        with app.app_context():
            record = BacdiveRecord.query.order_by(BacdiveRecord.bacdive_id).first()
            if not record:
                pytest.skip("知识库为空")
            bacdive_id = record.bacdive_id
        resp = super_client.get("/strain_showcase/", query_string={"q": str(bacdive_id)})
        assert resp.status_code == 200

    def test_detail_page(self, app, super_client):
        from app.models import BacdiveRecord
        with app.app_context():
            record = BacdiveRecord.query.order_by(BacdiveRecord.bacdive_id).first()
            if not record:
                pytest.skip("知识库为空")
            record_id = record.id
        resp = super_client.get(f"/strain_showcase/{record_id}")
        assert resp.status_code == 200
        assert "分类信息" in resp.get_data(as_text=True)

    def test_detail_missing_404(self, super_client):
        assert super_client.get("/strain_showcase/999999999").status_code == 404
