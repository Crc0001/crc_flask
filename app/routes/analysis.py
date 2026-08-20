from flask import Blueprint, current_app, render_template, request, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
from app.models.sample import Sample
from app.extensions import db

# 首先定义蓝图
analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")


def get_time_key(dt, granularity):
    """按粒度返回时间字符串"""
    if granularity == "day":
        return dt.strftime("%Y-%m-%d")
    elif granularity == "week":
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
    elif granularity == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")


@analysis_bp.context_processor
def inject_now():
    """向模板注入当前时间"""
    return {'now': datetime.now(), 'timedelta': timedelta}


@analysis_bp.route("/", methods=["GET"])
def index():
    # 获取当前日期和30天前的日期
    today = datetime.now()
    thirty_days_ago = today - timedelta(days=30)

    # 获取查询参数或使用默认值
    chart_type = request.args.get("type", "strain")
    granularity = request.args.get("granularity", "day")
    start_date = request.args.get("start_date", thirty_days_ago.strftime("%Y-%m-%d"))
    end_date = request.args.get("end_date", today.strftime("%Y-%m-%d"))

    return render_template(
        "analysis/index.html",
        chart_type=chart_type,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date
    )


@analysis_bp.route("/data", methods=["GET"])
def analysis_data():
    try:
        stat_type = request.args.get("type", "strain")  # strain / location
        granularity = request.args.get("granularity", "day")  # day / week / month
        start = request.args.get("start_date")
        end = request.args.get("end_date")

        # 构建查询
        query = db.session.query(Sample)

        # 过滤有检测时间的样本
        query = query.filter(Sample.last_detect_time.isnot(None))

        if start:
            try:
                start_date = datetime.strptime(start, "%Y-%m-%d")
                query = query.filter(Sample.last_detect_time >= start_date)
            except ValueError:
                return jsonify({"error": "开始时间格式错误"}), 400

        if end:
            try:
                end_date = datetime.strptime(end, "%Y-%m-%d")
                query = query.filter(Sample.last_detect_time <= end_date)
            except ValueError:
                return jsonify({"error": "结束时间格式错误"}), 400

        samples = query.all()

        # 数据统计
        stat = defaultdict(lambda: defaultdict(int))  # time_key -> key(strain/location) -> count

        for s in samples:
            if not s.last_detect_time:
                continue

            time_key = get_time_key(s.last_detect_time, granularity)

            if stat_type == "strain":
                # 菌种出现次数统计 - 每个样本计数为1，不管检测数量
                key = s.final_strain_name if s.final_strain_name else "未知菌种"
                # 每个样本计数为1，表示菌种出现次数
                count = 1
            else:
                # 采样地点统计
                key = s.collect_location if s.collect_location else "未知地点"
                count = 1  # 每个地点计数为1

            stat[time_key][key] += count

        # 转换为 Chart.js 适合的格式
        time_keys = sorted(stat.keys())
        all_keys = sorted({k for day in stat.values() for k in day.keys()})

        datasets = []
        for k in all_keys:
            datasets.append({
                "label": k,
                "data": [stat[tk].get(k, 0) for tk in time_keys],
            })

        return jsonify({
            "labels": time_keys,
            "datasets": datasets
        })

    except Exception as e:
        current_app.logger.error("趋势分析数据处理失败: %s", e, exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500