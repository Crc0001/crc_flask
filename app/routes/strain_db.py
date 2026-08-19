from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file
from app.models.sample import Sample
from app.extensions import db
from datetime import datetime
from io import BytesIO

strain_db_bp = Blueprint("strain_db", __name__, url_prefix="/strain_db")


@strain_db_bp.route("/", methods=["GET"])
def index():
    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # 搜索参数
    search_params = {
        'strain_name': request.args.get("strain_name", "").strip(),
        'location': request.args.get("location", "").strip(),
        'keyword': request.args.get("keyword", "").strip(),
        'start_date': request.args.get("start_date", ""),
        'end_date': request.args.get("end_date", ""),
    }

    query = Sample.query

    # 搜索过滤
    if search_params['strain_name']:
        query = query.filter(Sample.final_strain_name.ilike(f"%{search_params['strain_name']}%"))

    if search_params['location']:
        query = query.filter(Sample.collect_location == search_params['location'])

    if search_params['keyword']:
        query = query.filter(
            db.or_(
                Sample.sample_code.ilike(f"%{search_params['keyword']}%"),
                Sample.collector.ilike(f"%{search_params['keyword']}%")
            )
        )

    # 日期范围过滤
    try:
        if search_params['start_date']:
            start_dt = datetime.strptime(search_params['start_date'], "%Y-%m-%d")
            query = query.filter(Sample.collect_date >= start_dt)
        if search_params['end_date']:
            end_dt = datetime.strptime(search_params['end_date'], "%Y-%m-%d")
            query = query.filter(Sample.collect_date <= end_dt)
    except ValueError:
        pass

    # 分页查询（按录入/检测时间倒序，时间新的在前，id 倒序作次级排序）
    pagination = query.order_by(
        Sample.last_detect_time.desc(),
        Sample.id.desc()
    ).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 采集地点下拉框
    locations = db.session.query(Sample.collect_location) \
        .filter(Sample.collect_location.isnot(None)) \
        .distinct() \
        .order_by(Sample.collect_location) \
        .all()
    locations = [loc[0] for loc in locations if loc[0]]

    # 构建查询参数字符串（用于分页链接）
    query_string = ""
    if any(search_params.values()):
        params = []
        for key, value in search_params.items():
            if value:
                params.append(f"{key}={value}")
        if params:
            query_string = "&" + "&".join(params)

    # Ajax 请求只返回表格
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render_template(
            "strain_db/_table.html",
            samples=pagination.items,
            pagination=pagination,
            search=search_params,
            query_string=query_string
        )

    # 普通页面请求
    return render_template(
        "strain_db/index.html",
        samples=pagination.items,
        locations=locations,
        pagination=pagination,
        search=search_params,
        query_string=query_string
    )


# 新增：获取质谱图的接口
@strain_db_bp.route("/mass_spectrum/<int:sample_id>")
def get_mass_spectrum(sample_id):
    """获取质谱图"""
    sample = Sample.query.get_or_404(sample_id)

    if not sample.mass_spectrum:
        # 如果没有质谱图，返回一个透明的1x1像素图片
        from flask import Response
        import base64
        transparent_pixel = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        return Response(transparent_pixel, mimetype='image/png')

    # 返回二进制图片数据
    return send_file(
        BytesIO(sample.mass_spectrum),
        mimetype='image/png',  # 假设是PNG格式，你可以根据实际情况调整
        as_attachment=False
    )


# 保持 edit 和 delete 函数不变
@strain_db_bp.route("/edit/<int:sample_id>", methods=["GET", "POST"])
def edit(sample_id):
    sample = Sample.query.get_or_404(sample_id)

    if request.method == "POST":
        sample.sample_code = request.form.get("sample_code", sample.sample_code)
        sample.collector = request.form.get("collector", sample.collector)
        sample.collect_location = request.form.get("collect_location", sample.collect_location)

        # 处理日期
        collect_date_str = request.form.get("collect_date")
        if collect_date_str:
            try:
                sample.collect_date = datetime.strptime(collect_date_str, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "保存成功",
            "data": {
                "id": sample.id,
                "sample_code": sample.sample_code,
                "collector": sample.collector,
                "collect_location": sample.collect_location,
                "collect_date": sample.collect_date.strftime('%Y-%m-%d') if sample.collect_date else ''
            }
        })

    return render_template("strain_db/_edit_modal.html", sample=sample)


@strain_db_bp.route("/delete/<int:sample_id>", methods=["POST"])
def delete(sample_id):
    sample = Sample.query.get_or_404(sample_id)
    db.session.delete(sample)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "删除成功",
        "id": sample_id
    })