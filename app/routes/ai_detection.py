import base64
import json
import os
from datetime import datetime

import pandas as pd
import requests
from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.exceptions import HTTPException

from flask_login import current_user

from app.config import APP_ROLE
from app.extensions import db
from app.models.sample import Sample
from app.models.user import audit
from app.services.report_pdf import build_detection_report_pdf
from app.services.upload_guard import validate_image_upload

# vendor 模式才加载识别管线（torch/cv2/模型）；client 模式走我方远程 API
if APP_ROLE == "vendor":
    from app.services.recognition import run_recognition

ai_detection_bp = Blueprint("ai_detection", __name__)

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
MALDI_UPLOAD_DIR = "static/maldi_uploads"

# 上传扩展名白名单、魔数、尺寸与大小校验统一收敛在 services/upload_guard.py
_IMAGE_EXT_HINT = "png/jpg/jpeg/bmp/webp"

_DEMO_INPUT_RISK = {
    "level": "low",
    "label": "未启用",
    "score": 0.0,
    "soft_only": True,
    "temporary_gate": False,
    "message": "门禁已关闭（演示模式），Top3 直接来自封闭分类器与 XGBoost 打分。",
    "reasons": [],
    "signals": {},
}


def _read_upload_or_error():
    """校验并读取上传图片，返回 (filename, ext, image_bytes, error_message)。

    filename 为服务端生成的安全文件名（upload_<uuid>.<可信扩展名>），
    与原文件名解耦——杜绝用户可控扩展名（.html/.svg 等）落盘 static 目录。
    校验失败时前三个值为 None，error_message 为具体原因。
    """
    file = request.files.get("image")
    if not file or file.filename == "":
        return None, None, None, "请上传图片文件（{}）".format(_IMAGE_EXT_HINT)

    image_bytes = file.read()
    ok, message, safe_filename = validate_image_upload(file.filename, image_bytes)
    if not ok:
        return None, None, None, message

    ext = safe_filename.rsplit(".", 1)[1].lower() if "." in safe_filename else ""
    return safe_filename, ext, image_bytes, None


def _client_proxy_orb_detect(filename, image_bytes):
    """client 模式：转发我方模型服务 /api/v1/recognize，并把结果落盘到本地。

    filename 必须是 upload_guard 生成的安全文件名（已在调用方校验）。
    """
    base_url = (current_app.config.get("HWISHAI_API_BASE_URL") or "").rstrip("/")
    machine_token = current_app.config.get("HWISHAI_API_TOKEN") or ""
    if not base_url or not machine_token:
        return jsonify({
            "success": False,
            "message": "服务端未配置模型服务地址（HWISHAI_API_BASE_URL / HWISHAI_API_TOKEN）"
        })

    upload_dir = os.path.join(current_app.root_path, UPLOAD_DIR)
    result_dir = os.path.join(current_app.root_path, RESULT_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    image_path = os.path.join(upload_dir, filename)
    with open(image_path, "wb") as f:
        f.write(image_bytes)

    try:
        resp = requests.post(
            f"{base_url}/api/v1/recognize",
            files={"image": (filename, image_bytes, "application/octet-stream")},
            data={"with_result_image": "1"},
            headers={"Authorization": f"Bearer {machine_token}"},
            timeout=(5, int(current_app.config.get("HWISHAI_API_TIMEOUT", 300))),
        )
    except requests.RequestException as exc:
        current_app.logger.warning("转发我方模型服务失败: %s", exc)
        return jsonify({"success": False, "message": "无法连接我方模型服务，请稍后重试"})

    if resp.status_code == 401:
        return jsonify({"success": False, "message": "模型服务鉴权失败，请检查服务器配置的机器令牌"})
    if resp.status_code != 200:
        return jsonify({"success": False, "message": f"模型服务返回异常（HTTP {resp.status_code}）"})

    try:
        payload = resp.json()
    except ValueError:
        return jsonify({"success": False, "message": "模型服务返回内容无法解析"})

    if not payload.get("success"):
        return jsonify({"success": False, "message": payload.get("message") or "模型服务识别失败"})

    result_image_url = None
    result_b64 = payload.get("result_image_base64")
    result_filename = f"{os.path.splitext(filename)[0]}_classified.jpg"
    result_path = os.path.join(result_dir, result_filename)
    if result_b64:
        try:
            with open(result_path, "wb") as f:
                f.write(base64.b64decode(result_b64))
            result_image_url = url_for("static", filename=f"results/{result_filename}")
        except (ValueError, OSError) as exc:
            current_app.logger.warning("结果图落盘失败: %s", exc)

    top3 = payload.get("top3") or []
    top_candidates = []
    for item in top3:
        knowledge_record_id = item.get("knowledge_record_id")
        classifier_confidence = float(item.get("confidence", 0.0))
        top_candidates.append({
            "rank": item.get("rank", len(top_candidates) + 1),
            "matched_strain_id": item.get("matched_strain_id"),
            "matched_strain_name": item.get("matched_strain_name")
                or item.get("chinese_name")
                or item.get("species_name", ""),
            "classifier_species_name": item.get("species_name", ""),
            "classifier_chinese_name": item.get("chinese_name", ""),
            "classifier_confidence": classifier_confidence,
            "effective_confidence": classifier_confidence,
            "match_score": classifier_confidence,
            "image_score": classifier_confidence,
            "low_confidence": classifier_confidence < 0.5,
            "input_risk_level": (payload.get("input_risk") or {}).get("level", "medium"),
            "recognition_model": item.get("recognition_model") or payload.get("model", "HwishAI"),
            "knowledge_url": (
                url_for("strain_showcase.detail", record_id=knowledge_record_id)
                if knowledge_record_id
                else None
            ),
        })

    if not top_candidates:
        return jsonify({"success": False, "message": "HwishAI未返回菌种候选"})

    top_detection = top_candidates[0]
    input_risk = payload.get("input_risk") or dict(_DEMO_INPUT_RISK)
    plate_crop = payload.get("plate_crop") or {
        "detected": False, "applied": False, "confidence": None,
        "method": None, "needs_review": False, "review_reasons": [],
    }
    image_selection = payload.get("image_selection") or {"applied": False}
    low_confidence = bool(payload.get("low_confidence", False))

    selection_summary = (
        "大图已优先选取培养皿内部的孤立单菌落切片，"
        if image_selection.get("applied")
        else ""
    )
    risk_summary = input_risk.get("message", "软风险信号暂不可用，Top3仅作为候选结果。")
    analysis_text = (
        f"{selection_summary}"
        f"HwishAI已完成菌种识别。"
        f"当前最佳菌种：{top_detection.get('matched_strain_name', '未知菌种')}"
        f"（相对匹配度{top_detection.get('match_score', 0.0) * 100:.2f}%）。"
        f"{risk_summary}"
    )
    if low_confidence:
        analysis_text += "当前识别置信度较低，建议结合原始平板形态或其他检测结果复核。"

    audit(
        "detect_submit",
        f"提交菌种检测：Top1={top_detection.get('matched_strain_name', '未知')}"
        f"（{top_detection.get('match_score', 0) * 100:.1f}%）",
        username=current_user.username,
        ip=request.remote_addr,
    )
    return jsonify({
        "success": True,
        "accepted": True,
        "message": payload.get("message") or "HwishAI菌种识别完成（BioCLIP + XGBoost）",
        "candidates": top_candidates,
        "detections": [],
        "result_path": result_path if result_image_url else None,
        "result_image_url": result_image_url,
        "recommended_strain_name": top_detection.get("matched_strain_name", ""),
        "recommended_match_score": top_detection.get("match_score", 0.0),
        "input_risk": input_risk,
        "analysis_text": analysis_text,
        "plate_crop": plate_crop,
        "image_selection": image_selection,
        "low_confidence": low_confidence,
    })


@ai_detection_bp.route("/api/orb_detect", methods=["POST"])
def orb_detect():
    try:
        filename, ext, image_bytes, error_message = _read_upload_or_error()
        if filename is None:
            return jsonify({
                "success": False,
                "message": error_message or "请上传图片文件（{}）".format(_IMAGE_EXT_HINT)
            })

        if APP_ROLE == "client":
            return _client_proxy_orb_detect(filename, image_bytes)

        # ---- vendor：本地识别管线（filename 已是服务端生成的安全名） ----
        upload_dir = os.path.join(current_app.root_path, UPLOAD_DIR)
        result_dir = os.path.join(current_app.root_path, RESULT_DIR)
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)

        result = run_recognition(
            image_bytes,
            filename,
            upload_dir,
            result_dir,
            url_builder=lambda record_id: url_for(
                "strain_showcase.detail", record_id=record_id
            ),
        )
        if not result.get("ok"):
            return jsonify({"success": False, "message": result.get("message")})

        top_candidates = result["top_candidates"]
        top_detection = result["top_detection"]
        input_risk = result["input_risk"]
        plate_crop = result["plate_crop"]
        image_selection = result["image_selection"]
        low_confidence = result["low_confidence"]
        result_filename = result["result_filename"]

        selection_summary = (
            f"大图已优先选取培养皿内部的孤立单菌落切片，"
            if image_selection["applied"]
            else ""
        )
        risk_summary = input_risk.get(
            "message",
            "软风险信号暂不可用，Top3仅作为候选结果。",
        )
        analysis_text = (
            f"{selection_summary}"
            f"HwishAI已完成菌种识别。"
            f"当前最佳菌种：{top_detection.get('matched_strain_name', '未知菌种')}"
            f"（相对匹配度{top_detection.get('match_score', 0.0) * 100:.2f}%）。"
            f"{risk_summary}"
        )
        if low_confidence:
            analysis_text += "当前识别置信度较低，建议结合原始平板形态或其他检测结果复核。"

        audit(
            "detect_submit",
            f"提交菌种检测：Top1={top_detection.get('matched_strain_name', '未知')}"
            f"（{top_detection.get('match_score', 0) * 100:.1f}%）",
            username=current_user.username,
            ip=request.remote_addr,
        )
        return jsonify({
            "success": True,
            "accepted": True,
            "message": result["message"],
            "candidates": top_candidates,
            "detections": [],
            "result_path": result["result_path"],
            "result_image_url": url_for(
                "static",
                filename=f"results/{result_filename}",
            ),
            "recommended_strain_name": top_detection.get("matched_strain_name", ""),
            "recommended_match_score": top_detection.get("match_score", 0.0),
            "input_risk": input_risk,
            "analysis_text": analysis_text,
            "plate_crop": plate_crop,
            "image_selection": image_selection,
            "low_confidence": low_confidence,
        })
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error("菌落检测识别失败: %s", e, exc_info=True)
        return jsonify({"success": False, "message": "菌落检测识别失败，请稍后重试或更换图片"})


@ai_detection_bp.route("/ai_detection", methods=["GET"])
def ai_detection():
    # GET仅渲染页面，检测由上传接口按需执行；分类下拉数据由 /api/location_data 提供
    return render_template(
        "ai_detection.html",
        image_url=None,
        results=[],
        final_result=None,
        message=None,
        error_message=None,
        detect_count=0,
        maldi_image_url=None,
    )


@ai_detection_bp.route("/api/save_detection_report", methods=["POST"])
def save_detection_report():
    """保存检测报告到菌种数据库（sample表）"""
    try:
        sample_code = (request.form.get("sample_code") or "").strip()
        collect_date_str = (request.form.get("collect_date") or "").strip()
        source_location = (request.form.get("source_location") or "").strip()
        strain_name = (request.form.get("strain_name") or "").strip()

        if not sample_code:
            return jsonify({
                "success": False,
                "message": "缺少样品编号，请在报告中填写后再录入"
            })

        if not strain_name:
            return jsonify({
                "success": False,
                "message": "缺少菌种名称，请先完成菌落识别或手动填写"
            })

        collect_date = None
        if collect_date_str:
            try:
                collect_date = datetime.strptime(collect_date_str, "%Y-%m-%d")
            except ValueError:
                return jsonify({
                    "success": False,
                    "message": "采集日期格式错误，应为 YYYY-MM-DD"
                })

        maldi_file = request.files.get("maldi_image")
        mass_spectrum = None
        if maldi_file and maldi_file.filename:
            spectrum_bytes = maldi_file.read()
            ok, message, _ = validate_image_upload(maldi_file.filename, spectrum_bytes)
            if not ok:
                return jsonify({
                    "success": False,
                    "message": f"MALDI质谱图无效：{message}"
                })
            mass_spectrum = spectrum_bytes

        target = Sample.query.filter_by(sample_code=sample_code).first()
        now = datetime.now()

        if target:
            target.collect_date = collect_date
            target.collect_location = source_location or target.collect_location
            target.final_strain_name = strain_name
            target.last_detect_time = now
            target.last_detect_count = 1
            if mass_spectrum:
                target.mass_spectrum = mass_spectrum
            action = "updated"
        else:
            target = Sample(
                sample_code=sample_code,
                collect_date=collect_date,
                collect_location=source_location or None,
                final_strain_name=strain_name,
                last_detect_time=now,
                last_detect_count=1,
                mass_spectrum=mass_spectrum
            )
            db.session.add(target)
            action = "created"

        db.session.commit()

        audit(
            "report_save",
            f"录入检测报告：样品 {sample_code} → {strain_name}（{ '更新' if action == 'updated' else '新建' }）",
            username=current_user.username,
            ip=request.remote_addr,
        )
        return jsonify({
            "success": True,
            "message": "报告已录入菌种数据库(sample)",
            "sample_id": target.id,
            "action": action,
            "list_url": url_for("strain_db.index")
        })

    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("保存检测报告失败: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "message": "保存失败，请稍后重试"
        })


@ai_detection_bp.route("/api/check_sample_code", methods=["GET"])
def check_sample_code():
    """检查样品编号是否已存在于菌种数据库，存在则返回现有记录信息"""
    try:
        code = (request.args.get("sample_code") or "").strip()
        if not code:
            return jsonify({"success": True, "exists": False})

        target = Sample.query.filter_by(sample_code=code).first()
        if not target:
            return jsonify({"success": True, "exists": False})

        return jsonify({
            "success": True,
            "exists": True,
            "existing": {
                "sample_id": target.id,
                "strain_name": target.final_strain_name or "",
                "collect_date": target.collect_date.strftime("%Y-%m-%d") if target.collect_date else "",
                "location": target.collect_location or "",
                "last_detect_time": target.last_detect_time.strftime("%Y-%m-%d %H:%M") if target.last_detect_time else "",
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error("检查样品编号失败: %s", e, exc_info=True)
        return jsonify({"success": False, "message": "检查失败，请稍后重试"})


@ai_detection_bp.route('/api/export_detection_report_pdf', methods=['POST'])
def export_detection_report_pdf():
    try:
        sample_code = (request.form.get('sample_code') or '').strip()
        collect_date = (request.form.get('collect_date') or '').strip()
        source_location = (request.form.get('source_location') or '').strip()
        strain_name = (request.form.get('strain_name') or '').strip()
        detection_result = (request.form.get('detection_result') or '').strip()
        maldi_candidates_raw = (request.form.get('maldi_candidates') or '').strip()
        sequence_16s = (request.form.get('sequence_16s') or '').strip()
        result_16s_raw = (request.form.get('result_16s') or '').strip()
        image_file = request.files.get('image')
        if not image_file or not image_file.filename:
            return jsonify({'success': False, 'message': '请先上传样本图片'}), 400

        sample_image_bytes = image_file.read()
        ok, message, _ = validate_image_upload(image_file.filename, sample_image_bytes)
        if not ok:
            return jsonify({'success': False, 'message': f'样本图片无效：{message}'}), 400

        maldi_file = request.files.get('maldi_image')
        maldi_image_bytes = None
        if maldi_file and maldi_file.filename:
            maldi_image_bytes = maldi_file.read()
            ok, message, _ = validate_image_upload(maldi_file.filename, maldi_image_bytes)
            if not ok:
                return jsonify({'success': False, 'message': f'MALDI质谱图无效：{message}'}), 400

        try:
            maldi_candidates = json.loads(maldi_candidates_raw) if maldi_candidates_raw else []
        except (TypeError, ValueError):
            maldi_candidates = []
        if not isinstance(maldi_candidates, list):
            maldi_candidates = []

        try:
            result_16s = json.loads(result_16s_raw) if result_16s_raw else None
        except (TypeError, ValueError):
            result_16s = None
        if not isinstance(result_16s, dict):
            result_16s = None

        buffer = build_detection_report_pdf(
            sample_code=sample_code,
            collect_date=collect_date,
            source_location=source_location,
            strain_name=strain_name,
            detection_result=detection_result,
            maldi_candidates=maldi_candidates,
            sequence_16s=sequence_16s,
            result_16s=result_16s,
            sample_image_bytes=sample_image_bytes,
            maldi_image_bytes=maldi_image_bytes,
        )

        filename_code = sample_code or datetime.now().strftime('%Y%m%d_%H%M%S')
        audit(
            "report_pdf",
            f"导出检测报告PDF：样品 {sample_code or '未填写'}",
            username=current_user.username,
            ip=request.remote_addr,
        )
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'菌种检测报告_{filename_code}.pdf',
            mimetype='application/pdf'
        )
    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error("导出PDF失败: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': '导出PDF失败，请稍后重试'}), 500


@ai_detection_bp.route("/api/location_data", methods=["GET"])
def get_location_data():
    """API接口：获取分类数据"""
    hierarchical_data = SampleLite.get_hierarchical_data()
    return jsonify(hierarchical_data)


@ai_detection_bp.route("/ai_detection/get_excel_data", methods=["GET"])
def get_excel_data():
    """获取Excel文件数据并转换为HTML表格"""
    try:
        excel_path = os.path.join(current_app.root_path, 'static', 'maldi_results', 'analysis_result.xlsx')

        if not os.path.exists(excel_path):
            return jsonify({
                "success": False,
                "message": "Excel文件不存在",
                "html": """
                <div style="padding: 40px; text-align: center; color: #6c757d;">
                    <div style="font-size: 48px; margin-bottom: 20px;">❌</div>
                    <h4 style="color: #e74a3b; margin-bottom: 10px;">Excel文件未找到</h4>
                    <p>请将Excel文件放置在：static/maldi_results/analysis_result.xlsx</p>
                </div>
                """
            })

        # 读取Excel文件
        df = pd.read_excel(excel_path)

        # 转换为HTML表格（添加样式类）
        html_table = df.to_html(
            index=False,
            classes='excel-table',
            border=0,
            na_rep=''
        )

        # 美化HTML表格
        html = f"""
        <div class="excel-table-container">
            <div class="table-header">
                <h5>MALDI-TOF质谱分析结果</h5>
                <div class="table-info">
                    <span>数据来源：质谱分析系统</span>
                    <button class="btn-download" id="download-excel-btn">📥 导出Excel</button>
                </div>
            </div>
            <div class="table-wrapper">
                {html_table}
            </div>
        </div>
        """

        return jsonify({
            "success": True,
            "html": html,
            "filename": "analysis_result.xlsx",
            "download_url": url_for('static', filename='maldi_results/analysis_result.xlsx')
        })

    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error("读取Excel文件失败: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "message": "读取Excel文件失败，请检查文件格式是否正确",
            "html": """
            <div style="padding: 40px; text-align: center; color: #6c757d;">
                <div style="font-size: 48px; margin-bottom: 20px;">❌</div>
                <h4 style="color: #e74a3b; margin-bottom: 10px;">Excel文件读取失败</h4>
                <p style="margin-top: 20px;">请检查Excel文件格式是否正确</p>
            </div>
            """
        })


@ai_detection_bp.route("/download_excel", methods=["GET"])
def download_excel():
    """下载Excel文件"""
    excel_path = os.path.join(current_app.root_path, 'static', 'maldi_results', 'analysis_result.xlsx')

    if not os.path.exists(excel_path):
        return jsonify({
            "success": False,
            "message": "文件不存在"
        })

    return send_file(
        excel_path,
        as_attachment=True,
        download_name='maldi_analysis_result.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@ai_detection_bp.route("/api/upload_maldi_image", methods=["POST"])
def upload_maldi_image():
    """上传MALDI-TOF质谱图"""
    try:
        if 'maldi_image' not in request.files:
            return jsonify({
                "success": False,
                "message": "没有上传文件"
            })

        file = request.files['maldi_image']

        if file.filename == '':
            return jsonify({
                "success": False,
                "message": "没有选择文件"
            })

        # 类型/魔数/尺寸/大小校验 + 服务端生成的安全文件名
        image_bytes = file.read()
        ok, message, safe_filename = validate_image_upload(file.filename, image_bytes)
        if not ok:
            return jsonify({
                "success": False,
                "message": message
            })

        # 生成唯一的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"maldi_{timestamp}_{safe_filename}"

        # 保存文件
        upload_path = os.path.join(current_app.root_path, MALDI_UPLOAD_DIR, unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        with open(upload_path, "wb") as f:
            f.write(image_bytes)

        # 返回文件的URL路径
        image_url = url_for('static', filename=f'maldi_uploads/{unique_filename}')

        return jsonify({
            "success": True,
            "message": "质谱图上传成功",
            "image_url": image_url,
            "filename": unique_filename
        })

    except HTTPException:
        raise
    except Exception as e:
        current_app.logger.error("上传MALDI质谱图失败: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "message": "上传失败，请稍后重试"
        })
