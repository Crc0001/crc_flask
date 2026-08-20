"""检测报告 PDF 生成（双端共用，纯业务依赖 reportlab）。"""
import os
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def _get_pdf_chinese_font_name():
    candidates = [
        ("PDF_CN", r"C:\Windows\Fonts\msyh.ttc"),
        ("PDF_CN", r"C:\Windows\Fonts\simsun.ttc"),
        ("PDF_CN", r"C:\Windows\Fonts\simhei.ttf"),
        ("PDF_CN", r"C:\Windows\Fonts\simfang.ttf"),
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


def build_detection_report_pdf(
    sample_code="",
    collect_date="",
    source_location="",
    strain_name="",
    detection_result="",
    maldi_candidates=None,
    sequence_16s="",
    result_16s=None,
    sample_image_bytes=None,
    maldi_image_bytes=None,
):
    """生成检测报告 PDF，返回 BytesIO（调用方负责 send_file）。"""
    font_name = _get_pdf_chinese_font_name()
    if not font_name:
        raise ValueError("未找到可用中文字体，请检查服务器字体配置")

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

    # 补充检测信息独立成页，避免长 16S 序列挤压首页图片。
    pdf.showPage()
    y = page_height - 50
    pdf.setFont(font_name, 14)
    pdf.drawString(40, y, '补充检测结果')
    y -= 28

    def ensure_detail_space(required_height=24):
        nonlocal y
        if y < 45 + required_height:
            pdf.showPage()
            y = page_height - 50

    def draw_detail_heading(title):
        nonlocal y
        ensure_detail_space(34)
        pdf.setFont(font_name, 12)
        pdf.drawString(40, y, title)
        y -= 20

    def draw_detail_text(text, font_size=10, line_height=15, x=48):
        nonlocal y
        max_width = page_width - x - 40
        source_lines = str(text or '').splitlines() or ['']
        for source_line in source_lines:
            wrapped_lines = []
            line = ''
            for ch in source_line:
                candidate = line + ch
                if pdf.stringWidth(candidate, font_name, font_size) <= max_width:
                    line = candidate
                else:
                    if line:
                        wrapped_lines.append(line)
                    line = ch
            wrapped_lines.append(line)
            for wrapped_line in wrapped_lines:
                ensure_detail_space(line_height)
                pdf.setFont(font_name, font_size)
                pdf.drawString(x, y, wrapped_line)
                y -= line_height

    def report_percent(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return '-'
        if abs(number) <= 1:
            number *= 100
        return f'{number:.2f}%'

    draw_detail_heading('MALDI-TOF检测结果')
    if maldi_candidates:
        for index, candidate in enumerate(maldi_candidates[:5], start=1):
            if not isinstance(candidate, dict):
                continue
            strain = candidate.get('strain_name') or '未知菌种'
            scientific = candidate.get('scientific_name') or '-'
            score = report_percent(candidate.get('score'))
            cosine = report_percent(candidate.get('cosine_sim'))
            matched_count = candidate.get('matched_count', '-')
            draw_detail_text(
                f'{index}. {strain}（{scientific}）  综合得分：{score}；'
                f'余弦相似度：{cosine}；匹配峰数：{matched_count}'
            )
    else:
        draw_detail_text('未进行 MALDI-TOF 检测或未获得匹配结果。')
    y -= 8

    draw_detail_heading('16S序列')
    compact_sequence = ''.join(sequence_16s.split())
    draw_detail_text(compact_sequence or '未提交 16S 序列。', font_size=9, line_height=13)
    y -= 8

    draw_detail_heading('16S RNA检测结果')
    if result_16s:
        similarity = report_percent(result_16s.get('similarity'))
        query_length = result_16s.get('query_length') or len(compact_sequence) or '-'
        draw_detail_text(f'匹配菌种：{result_16s.get("strain_name") or "未知菌种"}')
        draw_detail_text(f'拉丁名：{result_16s.get("scientific_name") or "-"}')
        draw_detail_text(f'相似度：{similarity}')
        draw_detail_text(f'最长匹配长度：{result_16s.get("match_length") or "-"} bp')
        draw_detail_text(f'查询长度：{query_length} bp')
        draw_detail_text(f'参考长度：{result_16s.get("ref_length") or "-"} bp')
    else:
        draw_detail_text('未进行 16S RNA 检测或未获得匹配结果。')

    pdf.save()
    buffer.seek(0)
    return buffer
