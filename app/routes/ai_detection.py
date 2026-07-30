import os
import json
import random
import shutil
import uuid
from io import BytesIO
from datetime import datetime
from flask import Blueprint, render_template, request, current_app, url_for, jsonify
from werkzeug.utils import secure_filename
import cv2
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models.sample_lite import SampleLite
from app.models.sample import Sample
from app.models import Strain
from app.extensions import db
from app.services.yolo_service import (
    HWISHAI_CLASSIFIER_MODEL,
    classify_images,
    detect_and_draw,
)
from crop_plate_batch import crop_plate
from image_slicer import slice_images
import pandas as pd
from flask import send_file

ai_detection_bp = Blueprint("ai_detection", __name__)

UPLOAD_DIR = "static/uploads"
RESULT_DIR = "static/results"
MALDI_UPLOAD_DIR = "static/maldi_uploads"
ENABLE_PLATE_CROP = False  # 暂时停用，保留裁剪实现供后续恢复
SLICE_TRIGGER_SIZE = 1280
SLICE_SIZE = 448
SLICE_SAMPLE_COUNT = 20


def _strain_match_candidates():
    strains = Strain.query.filter(Strain.is_active.is_(True)).all()
    return [
        {
            "strain_id": strain.id,
            "strain_name": strain.name or strain.scientific_name or f"菌种#{strain.id}",
            "scientific_name": strain.scientific_name or "",
            "alias": strain.alias or "",
            "category": strain.category or "",
        }
        for strain in strains
    ]


def _read_image_bgr(image_bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _read_image_bgr_from_path(image_path):
    try:
        arr = np.fromfile(image_path, dtype=np.uint8)
        if arr.size == 0:
            return None
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def _center_crop(img_bgr, crop_ratio=0.8):
    crop_ratio = float(np.clip(crop_ratio, 0.3, 1.0))
    if crop_ratio >= 0.999:
        return img_bgr

    h, w = img_bgr.shape[:2]
    ch, cw = int(h * crop_ratio), int(w * crop_ratio)
    y1 = (h - ch) // 2
    x1 = (w - cw) // 2
    return img_bgr[y1:y1 + ch, x1:x1 + cw]


def _select_detection_image(image, image_path, upload_dir):
    height, width = image.shape[:2]
    selection = {
        "applied": False,
        "original_size": [int(width), int(height)],
        "tile_size": None,
        "total_tiles": 0,
        "sampled_tiles": 1,
        "selected_tile": None,
        "confidence": None,
    }
    if width <= SLICE_TRIGGER_SIZE and height <= SLICE_TRIGGER_SIZE:
        return image, image_path, None, selection

    slice_root = os.path.join(upload_dir, "detection_slices", uuid.uuid4().hex)
    source_dir = os.path.join(slice_root, "source")
    tile_dir = os.path.join(slice_root, "tiles")
    os.makedirs(source_dir, exist_ok=True)
    source_ext = os.path.splitext(image_path)[1] or ".jpg"
    source_path = os.path.join(source_dir, f"source_{uuid.uuid4().hex}{source_ext}")
    shutil.copy2(image_path, source_path)

    slice_images(
        source_dir,
        output_dir=tile_dir,
        slice_size=SLICE_SIZE,
        overlap_ratio=0.2,
        recursive=False,
        min_std=0,
        min_edges=0,
    )
    tile_paths = sorted(
        os.path.join(tile_dir, name)
        for name in os.listdir(tile_dir)
        if name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"))
    )
    if not tile_paths:
        raise ValueError("大图切片后没有生成可检测图片")

    sampled_paths = random.sample(tile_paths, min(SLICE_SAMPLE_COUNT, len(tile_paths)))
    sampled_images = []
    readable_paths = []
    for tile_path in sampled_paths:
        tile = _read_image_bgr_from_path(tile_path)
        if tile is not None:
            sampled_images.append(tile)
            readable_paths.append(tile_path)
    if not sampled_images:
        raise ValueError("随机抽取的切片均无法读取")

    classifications = classify_images(sampled_images)
    best_index = max(
        range(len(classifications)),
        key=lambda index: float(classifications[index].get("confidence", 0.0)),
    )
    best_path = readable_paths[best_index]
    best_classification = classifications[best_index]
    selection.update({
        "applied": True,
        "tile_size": [SLICE_SIZE, SLICE_SIZE],
        "total_tiles": len(tile_paths),
        "sampled_tiles": len(sampled_images),
        "selected_tile": os.path.basename(best_path),
        "confidence": round(float(best_classification.get("confidence", 0.0)), 6),
        "_work_dir": slice_root,
    })
    return sampled_images[best_index], best_path, best_classification, selection


def _preprocess_for_match(img_bgr, size=256, crop_ratio=0.8):
    cropped = _center_crop(img_bgr, crop_ratio=crop_ratio)
    return cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)


def _normalize_gray_for_features(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _ratio_good_matches(des1, des2, norm_type, ratio=0.75):
    bf = cv2.BFMatcher(norm_type, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)

    good = 0
    for m_n in matches:
        if len(m_n) < 2:
            continue
        m, n = m_n
        if m.distance < ratio * n.distance:
            good += 1
    return good


def _orb_similarity(q_img, db_img):
    gray_q = _normalize_gray_for_features(q_img)
    gray_d = _normalize_gray_for_features(db_img)

    orb = cv2.ORB_create(nfeatures=1500)
    kp1, des1 = orb.detectAndCompute(gray_q, None)
    kp2, des2 = orb.detectAndCompute(gray_d, None)

    if des1 is not None and des2 is not None and len(kp1) >= 10 and len(kp2) >= 10:
        good = _ratio_good_matches(des1, des2, cv2.NORM_HAMMING, ratio=0.75)
        denom = max(min(len(kp1), len(kp2)), 1)
        return float(np.clip(good / float(denom), 0.0, 1.0))

    akaze = cv2.AKAZE_create()
    kp1, des1 = akaze.detectAndCompute(gray_q, None)
    kp2, des2 = akaze.detectAndCompute(gray_d, None)
    if des1 is None or des2 is None or len(kp1) == 0 or len(kp2) == 0:
        return 0.0

    good = _ratio_good_matches(des1, des2, cv2.NORM_HAMMING, ratio=0.78)
    denom = max(min(len(kp1), len(kp2)), 1)
    return float(np.clip(good / float(denom), 0.0, 1.0))


def _color_hist_similarity(q_img, db_img):
    hsv_q = cv2.cvtColor(q_img, cv2.COLOR_BGR2HSV)
    hsv_d = cv2.cvtColor(db_img, cv2.COLOR_BGR2HSV)

    hist_size = [32, 32]
    ranges = [0, 180, 0, 256]
    channels = [0, 1]

    hq = cv2.calcHist([hsv_q], channels, None, hist_size, ranges)
    hd = cv2.calcHist([hsv_d], channels, None, hist_size, ranges)
    cv2.normalize(hq, hq, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(hd, hd, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    corr = cv2.compareHist(hq, hd, cv2.HISTCMP_CORREL)
    return float(np.clip((corr + 1.0) / 2.0, 0.0, 1.0))


@ai_detection_bp.route("/api/orb_detect", methods=["POST"])
def orb_detect():
    try:
        file = request.files.get("image")
        if not file or file.filename == "":
            return jsonify({"success": False, "message": "请上传图片文件"})

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'jfif', 'heic', 'heif'}

        mime_type = (file.mimetype or '').lower()
        is_image_mime = mime_type.startswith('image/')
        is_allowed_ext = ext in allowed_extensions

        if not is_image_mime and not is_allowed_ext:
            return jsonify({
                "success": False,
                "message": "不支持的文件格式，请上传图片文件（png/jpg/jpeg/gif/bmp/tiff/webp/jfif/heic/heif）"
            })

        image_bytes = file.read()
        if not image_bytes:
            return jsonify({"success": False, "message": "图片内容为空"})

        upload_dir = os.path.join(current_app.root_path, UPLOAD_DIR)
        result_dir = os.path.join(current_app.root_path, RESULT_DIR)
        os.makedirs(upload_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)

        stem, original_ext = os.path.splitext(filename)
        filename = f"{stem or 'upload'}_{uuid.uuid4().hex[:12]}{original_ext or '.jpg'}"
        image_path = os.path.join(upload_dir, filename)
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        q_raw = _read_image_bgr(image_bytes)
        if q_raw is None:
            return jsonify({"success": False, "message": "图片读取失败，请更换图片重试"})

        plate_crop = {
            "detected": False,
            "applied": False,
            "confidence": None,
            "method": None,
            "needs_review": False,
            "review_reasons": [],
        }
        detection_image = q_raw
        if ENABLE_PLATE_CROP:
            try:
                detection_image, crop_detection = crop_plate(q_raw)
                plate_crop.update({
                    "detected": True,
                    "applied": True,
                    "confidence": round(float(crop_detection.confidence), 6),
                    "method": crop_detection.method,
                    "needs_review": crop_detection.needs_review,
                    "review_reasons": list(crop_detection.review_reasons),
                    "bbox": [
                        crop_detection.x1,
                        crop_detection.y1,
                        crop_detection.x2,
                        crop_detection.y2,
                    ],
                    "output_size": [
                        int(detection_image.shape[1]),
                        int(detection_image.shape[0]),
                    ],
                })
            except (ValueError, cv2.error) as exc:
                plate_crop["reason"] = str(exc)

        detection_image, detection_image_path, selected_classification, image_selection = (
            _select_detection_image(detection_image, image_path, upload_dir)
        )
        strain_candidates = _strain_match_candidates()

        try:
            detection_result = detect_and_draw(
                image_path=detection_image_path,
                save_dir=result_dir,
                confidence_threshold=0.5,
                strain_candidates=strain_candidates,
                image_bgr=detection_image,
                image_classification=selected_classification,
            )
        finally:
            slice_work_dir = image_selection.pop("_work_dir", None)
            if slice_work_dir:
                shutil.rmtree(slice_work_dir, ignore_errors=True)

        detections = detection_result.get("detections") or []
        if not detection_result.get("success"):
            return jsonify({"success": False, "message": detection_result.get("error") or "菌落检测识别失败"})

        classification = detection_result.get("classification") or {}
        if image_selection.get("confidence") is None:
            image_selection["confidence"] = round(
                float(classification.get("confidence", 0.0)),
                6,
            )
        if not classification.get("top3"):
            return jsonify({"success": False, "message": "HwishAI未返回菌种候选"})

        strain_by_scientific_name = {
            " ".join(candidate.get("scientific_name", "").split()).casefold(): candidate
            for candidate in strain_candidates
            if candidate.get("scientific_name")
        }
        classifier_aliases = {
            "Faucicola osloensis": "Moraxella osloensis",
            "Staphylococcus ureilyticu": "Staphylococcus ureilyticus",
        }
        top_candidates = []
        for rank, item in enumerate(classification["top3"], start=1):
            scientific_name = item.get("species_name", "")
            lookup_name = classifier_aliases.get(scientific_name, scientific_name)
            strain = strain_by_scientific_name.get(
                " ".join(lookup_name.split()).casefold()
            )
            classifier_confidence = float(item.get("confidence", 0.0))
            classifier_chinese_name = item.get("chinese_name", "")
            top_candidates.append({
                "rank": rank,
                "matched_strain_id": strain.get("strain_id") if strain else None,
                "matched_strain_name": (
                    strain.get("strain_name")
                    if strain
                    else classifier_chinese_name or scientific_name
                ),
                "classifier_species_name": scientific_name,
                "classifier_chinese_name": classifier_chinese_name,
                "classifier_confidence": classifier_confidence,
                "match_score": classifier_confidence,
                "image_score": classifier_confidence,
                "low_confidence": classifier_confidence < 0.5,
                "recognition_model": f"HwishAI {HWISHAI_CLASSIFIER_MODEL}",
            })

        if not top_candidates:
            top_candidates = [detections[0]]
        top_detection = top_candidates[0]
        yolo_summary = f"YOLO已框选{len(detections)}个菌落，" if detections else ""
        selection_summary = (
            f"大图随机抽检{image_selection['sampled_tiles']}张切片并选取最高置信度切片，"
            if image_selection["applied"]
            else ""
        )
        analysis_text = (
            f"{selection_summary}"
            f"{yolo_summary}HwishAI已完成菌种识别。"
            f"当前最佳菌种：{top_detection.get('matched_strain_name', '未知菌种')}（{top_detection.get('match_score', 0.0) * 100:.2f}%）。"
        )

        return jsonify({
            "success": True,
            "message": "YOLO框选与HwishAI识别完成",
            "candidates": top_candidates,
            "detections": detections,
            "result_path": detection_result.get("result_path"),
            "result_image_url": url_for(
                "static",
                filename=f"results/{os.path.basename(detection_image_path)}",
            ),
            "recommended_strain_name": top_detection.get("matched_strain_name", ""),
            "recommended_match_score": top_detection.get("match_score", 0.0),
            "analysis_text": analysis_text,
            "plate_crop": plate_crop,
            "image_selection": image_selection,
        })
    except Exception as e:
        print(f"菌落检测识别失败: {str(e)}")
        return jsonify({"success": False, "message": f"菌落检测识别失败: {str(e)}"})


@ai_detection_bp.route("/ai_detection", methods=["GET"])
def ai_detection():
    # GET仅渲染页面，检测由上传接口按需执行
    location_hierarchy = SampleLite.get_hierarchical_data()
    return render_template(
        "ai_detection.html",
        image_url=None,
        results=[],
        final_result=None,
        message=None,
        error_message=None,
        detect_count=0,
        maldi_image_url=None,
        location_hierarchy=json.dumps(location_hierarchy)
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
        mass_spectrum = maldi_file.read() if maldi_file and maldi_file.filename else None

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

        return jsonify({
            "success": True,
            "message": "报告已录入菌种数据库(sample)",
            "sample_id": target.id,
            "action": action,
            "list_url": url_for("strain_db.index")
        })

    except Exception as e:
        db.session.rollback()
        print(f"保存检测报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"保存失败: {str(e)}"
        })


def _get_pdf_chinese_font_name():
    candidates = [
        ("PDF_CN", r"C:\\Windows\\Fonts\\msyh.ttc"),
        ("PDF_CN", r"C:\\Windows\\Fonts\\simsun.ttc"),
        ("PDF_CN", r"C:\\Windows\\Fonts\\simhei.ttf"),
        ("PDF_CN", r"C:\\Windows\\Fonts\\simfang.ttf"),
    ]

    for font_name, font_path in candidates:
        if not os.path.exists(font_path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return font_name
        except Exception:
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path, subfontIndex=0))
                return font_name
            except Exception:
                continue

    return None


def _draw_wrapped_text(pdf, text, x, y, max_width, font_name, font_size, line_height=18):
    content = text or ''
    if not content:
        return y - line_height

    pdf.setFont(font_name, font_size)
    line = ''
    for ch in content:
        candidate = line + ch
        if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
            line = candidate
        else:
            if line:
                pdf.drawString(x, y, line)
                y -= line_height
            line = ch

    if line:
        pdf.drawString(x, y, line)
        y -= line_height

    return y


def _draw_image(pdf, image_bytes, title, x, y, font_name, width=240, height=160):
    pdf.setFont(font_name, 11)
    pdf.drawString(x, y, title)
    y -= 12

    if not image_bytes:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y - 18, '未上传')
        return y - height

    try:
        image = ImageReader(BytesIO(image_bytes))
        pdf.drawImage(image, x, y - height, width=width, height=height, preserveAspectRatio=True, anchor='c')
    except Exception:
        pdf.setFont(font_name, 10)
        pdf.drawString(x, y - 18, '图片读取失败')

    return y - height


@ai_detection_bp.route('/api/export_detection_report_pdf', methods=['POST'])
def export_detection_report_pdf():
    try:
        sample_code = (request.form.get('sample_code') or '').strip()
        collect_date = (request.form.get('collect_date') or '').strip()
        source_location = (request.form.get('source_location') or '').strip()
        strain_name = (request.form.get('strain_name') or '').strip()
        detection_result = (request.form.get('detection_result') or '').strip()
        image_file = request.files.get('image')
        if not image_file or not image_file.filename:
            return jsonify({'success': False, 'message': '请先上传样本图片'}), 400

        sample_image_bytes = image_file.read()
        maldi_file = request.files.get('maldi_image')
        maldi_image_bytes = maldi_file.read() if maldi_file and maldi_file.filename else None

        font_name = _get_pdf_chinese_font_name()
        if not font_name:
            return jsonify({'success': False, 'message': '未找到可用中文字体，请检查服务器字体配置'}), 500

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        page_width, page_height = A4

        y = page_height - 50
        pdf.setFont(font_name, 16)
        pdf.drawString(40, y, '菌种检测报告')
        y -= 28

        pdf.setFont(font_name, 11)
        y = _draw_wrapped_text(pdf, f'样品编号：{sample_code or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y = _draw_wrapped_text(pdf, f'采集日期：{collect_date or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y = _draw_wrapped_text(pdf, f'来源位置：{source_location or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y = _draw_wrapped_text(pdf, f'菌种名称：{strain_name or "未填写"}', 40, y, page_width - 80, font_name, 11, line_height=16)
        y -= 8

        pdf.setFont(font_name, 11)
        pdf.drawString(40, y, '检测结论：')
        y -= 18

        conclusion_text = (detection_result or strain_name or '未填写').splitlines() or ['未填写']
        for line in conclusion_text:
            y = _draw_wrapped_text(pdf, line, 40, y, page_width - 80, font_name, 10, line_height=15)
            if y < 260:
                pdf.showPage()
                y = page_height - 50
                pdf.setFont(font_name, 10)

        if y < 260:
            pdf.showPage()
            y = page_height - 50

        left_x = 40
        right_x = page_width / 2 + 10
        image_top_y = y
        _draw_image(pdf, sample_image_bytes, '样本图片', left_x, image_top_y, font_name)
        _draw_image(pdf, maldi_image_bytes, 'MALDI-TOF图谱', right_x, image_top_y, font_name)

        pdf.save()
        buffer.seek(0)

        filename_code = sample_code or datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'菌种检测报告_{filename_code}.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f'导出PDF失败: {str(e)}')
        return jsonify({'success': False, 'message': f'导出PDF失败: {str(e)}'}), 500


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

        # 打印路径和存在性
        print("Excel文件路径:", excel_path)
        print("文件是否存在:", os.path.exists(excel_path))

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

    except Exception as e:
        print(f"读取Excel文件失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"读取Excel文件失败: {str(e)}",
            "html": f"""
            <div style="padding: 40px; text-align: center; color: #6c757d;">
                <div style="font-size: 48px; margin-bottom: 20px;">❌</div>
                <h4 style="color: #e74a3b; margin-bottom: 10px;">Excel文件读取失败</h4>
                <p>{str(e)}</p>
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

        # 检查文件类型
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext not in allowed_extensions:
            return jsonify({
                "success": False,
                "message": "不支持的文件格式，请上传图片文件（png, jpg, jpeg, gif, bmp, tiff）"
            })

        # 生成唯一的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"maldi_{timestamp}_{filename}"

        # 保存文件
        upload_path = os.path.join(current_app.root_path, MALDI_UPLOAD_DIR, unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)

        # 返回文件的URL路径
        image_url = url_for('static', filename=f'maldi_uploads/{unique_filename}')

        return jsonify({
            "success": True,
            "message": "质谱图上传成功",
            "image_url": image_url,
            "filename": unique_filename
        })

    except Exception as e:
        print(f"上传MALDI质谱图失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"上传失败: {str(e)}"
        })


@ai_detection_bp.route("/api/analyze_maldi", methods=["POST"])
def analyze_maldi():
    """分析MALDI-TOF数据文件（CSV/Excel）并返回分析结果"""
    try:
        if 'maldi_file' not in request.files:
            return jsonify({
                "success": False,
                "message": "没有上传文件"
            })

        file = request.files['maldi_file']

        if file.filename == '':
            return jsonify({
                "success": False,
                "message": "没有选择文件"
            })

        # 检查文件类型
        allowed_extensions = {'csv', 'xlsx', 'xls'}
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext not in allowed_extensions:
            return jsonify({
                "success": False,
                "message": "不支持的文件格式，请上传CSV或Excel文件"
            })

        # 生成唯一的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"maldi_data_{timestamp}_{filename}"

        # 保存文件
        upload_path = os.path.join(current_app.root_path, MALDI_UPLOAD_DIR, unique_filename)
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        file.save(upload_path)

        # 这里可以添加实际的分析逻辑
        # 暂时模拟分析结果
        import random
        confidence = round(95 + random.random() * 4, 2)

        # 模拟菌种列表
        strains = [
            "Lactobacillus helveticus",
            "Lactobacillus acidophilus",
            "Escherichia coli",
            "Staphylococcus aureus",
            "Bacillus subtilis"
        ]
        detected_strain = random.choice(strains)

        return jsonify({
            "success": True,
            "message": "质谱分析完成",
            "strain_name": detected_strain,
            "confidence": confidence,
            "filename": unique_filename
        })

    except Exception as e:
        print(f"分析MALDI数据失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"分析失败: {str(e)}"
        })
