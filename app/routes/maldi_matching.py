"""
MALDI-TOF 质谱匹配路由

提供质谱匹配和参考谱管理的 API 接口
"""

from flask import Blueprint, request, jsonify, current_app, render_template
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models.maldi_reference import MaldiReference
from app.models.strain import Strain, Strain16S
from app.services.maldi_matching import (
    parse_maldi_txt_from_bytes,
    match_query_against_references,
    normalize_peaks
)
from app.services.spectrum_plot import generate_comparison_plot
from datetime import datetime
from difflib import SequenceMatcher

maldi_matching_bp = Blueprint('maldi_matching', __name__)


@maldi_matching_bp.route('/maldi_matching', methods=['GET'])
def maldi_matching_page():
    """质谱匹配页面"""
    return render_template('maldi_matching.html')


@maldi_matching_bp.route('/api/maldi/match', methods=['POST'])
def maldi_match():
    """
    质谱匹配接口

    接收上传的 TXT 文件，解析峰数据，与库中所有参考谱匹配，返回 Top-K 结果

    Request:
        - file: TXT 文件（multipart/form-data）
        - top_k: 返回前K个结果（可选，默认3）
        - mz_tolerance: m/z 容差（可选，默认0.5）
        - min_intensity_ratio: 最小强度阈值（可选，默认0.01）

    Response:
        {
            "success": true,
            "candidates": [
                {
                    "strain_id": int,
                    "strain_name": str,
                    "scientific_name": str,
                    "sample_id": str,
                    "score": float,
                    "cosine_sim": float,
                    "query_coverage": float,
                    "ref_coverage": float,
                    "matched_count": int
                },
                ...
            ],
            "query_info": {
                "sample_id": str or null,
                "peak_count": int
            }
        }
    """
    try:
        # 检查文件
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': '没有上传文件'
            })

        file = request.files['file']

        if file.filename == '':
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            })

        # 检查文件类型
        if not file.filename.lower().endswith('.txt'):
            return jsonify({
                'success': False,
                'message': '只支持 TXT 文件格式'
            })

        # 读取文件内容
        file_bytes = file.read()

        # 解析文件
        parsed_data = parse_maldi_txt_from_bytes(file_bytes)

        if not parsed_data['peaks']:
            return jsonify({
                'success': False,
                'message': '文件中没有有效的峰数据'
            })

        # 获取参数
        top_k = int(request.form.get('top_k', 3))
        mz_tolerance = float(request.form.get('mz_tolerance', 0.5))
        min_intensity_ratio = float(request.form.get('min_intensity_ratio', 0.01))

        # 查询所有参考谱
        references = MaldiReference.query.join(Strain).filter(Strain.is_active == True).all()

        if not references:
            return jsonify({
                'success': False,
                'message': '质谱参考库为空，请先添加参考谱'
            })

        # 匹配
        candidates = match_query_against_references(
            query_peaks=parsed_data['peaks'],
            references=references,
            mz_tolerance=mz_tolerance,
            min_intensity_ratio=min_intensity_ratio,
            top_k=top_k
        )

        if not candidates:
            return jsonify({
                'success': False,
                'message': '未找到匹配的参考谱'
            })

        # 生成对比图（查询样本 vs Top-1 参考谱）
        comparison_plot_base64 = None
        if candidates:
            try:
                # 获取 Top-1 参考谱
                top_candidate = candidates[0]
                ref_id = top_candidate['reference_id']

                # 从数据库获取完整的参考谱数据
                ref_reference = MaldiReference.query.get(ref_id)

                if ref_reference and ref_reference.peaks:
                    # 归一化查询峰和参考峰
                    normalized_query = normalize_peaks(parsed_data['peaks'])
                    normalized_ref = ref_reference.peaks

                    # 生成对比图
                    comparison_plot_base64 = generate_comparison_plot(
                        query_peaks=normalized_query,
                        ref_peaks=normalized_ref,
                        query_sample_id=parsed_data.get('sample_id'),
                        ref_sample_id=ref_reference.sample_id,
                        ref_strain_name=top_candidate.get('strain_name')
                    )
            except Exception as plot_error:
                current_app.logger.warning(f"生成对比图失败: {str(plot_error)}")
                comparison_plot_base64 = None

        return jsonify({
            'success': True,
            'candidates': candidates,
            'query_info': {
                'sample_id': parsed_data['sample_id'],
                'peak_count': parsed_data['peak_count']
            },
            'comparison_plot': comparison_plot_base64  # base64 编码的 PNG 图片
        })

    except Exception as e:
        current_app.logger.error(f"质谱匹配失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'匹配失败: {str(e)}'
        })


@maldi_matching_bp.route('/api/maldi/reference/add', methods=['POST'])
def add_reference():
    """
    添加参考谱到库

    Request:
        - file: TXT 文件（multipart/form-data）
        - strain_id: 菌种ID

    Response:
        {
            "success": true,
            "reference": {
                "id": int,
                "strain_id": int,
                "strain_name": str,
                "sample_id": str,
                "peak_count": int
            }
        }
    """
    try:
        # 检查文件
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': '没有上传文件'
            })

        file = request.files['file']

        if file.filename == '':
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            })

        # 检查文件类型
        if not file.filename.lower().endswith('.txt'):
            return jsonify({
                'success': False,
                'message': '只支持 TXT 文件格式'
            })

        # 获取 strain_id
        strain_id = request.form.get('strain_id')

        if not strain_id:
            return jsonify({
                'success': False,
                'message': '缺少 strain_id 参数'
            })

        try:
            strain_id = int(strain_id)
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'strain_id 必须是整数'
            })

        # 检查菌种是否存在
        strain = Strain.query.get(strain_id)

        if not strain:
            return jsonify({
                'success': False,
                'message': f'菌种 ID {strain_id} 不存在'
            })

        # 读取并解析文件
        file_bytes = file.read()
        parsed_data = parse_maldi_txt_from_bytes(file_bytes)

        if not parsed_data['peaks']:
            return jsonify({
                'success': False,
                'message': '文件中没有有效的峰数据'
            })

        # 归一化峰数据
        from app.services.maldi_matching import normalize_peaks
        normalized_peaks = normalize_peaks(parsed_data['peaks'])

        # 创建参考谱记录
        reference = MaldiReference(
            strain_id=strain_id,
            sample_id=parsed_data['sample_id'],
            peaks=normalized_peaks,
            peak_count=len(normalized_peaks)
        )

        db.session.add(reference)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '参考谱添加成功',
            'reference': {
                'id': reference.id,
                'strain_id': reference.strain_id,
                'strain_name': strain.name,
                'sample_id': reference.sample_id,
                'peak_count': reference.peak_count
            }
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"添加参考谱失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'添加失败: {str(e)}'
        })


@maldi_matching_bp.route('/api/maldi/reference/list', methods=['GET'])
def list_references():
    """
    列出所有参考谱

    Query params:
        - strain_id: 可选，按菌种ID过滤

    Response:
        {
            "success": true,
            "references": [
                {
                    "id": int,
                    "strain_id": int,
                    "strain_name": str,
                    "scientific_name": str,
                    "sample_id": str,
                    "peak_count": int,
                    "created_at": str
                },
                ...
            ]
        }
    """
    try:
        # 获取过滤参数
        strain_id_filter = request.args.get('strain_id')

        # 构建查询
        query = MaldiReference.query.join(Strain)

        if strain_id_filter:
            try:
                strain_id = int(strain_id_filter)
                query = query.filter(MaldiReference.strain_id == strain_id)
            except ValueError:
                pass

        references = query.order_by(MaldiReference.created_at.desc()).all()

        return jsonify({
            'success': True,
            'references': [ref.to_dict() for ref in references]
        })

    except Exception as e:
        current_app.logger.error(f"获取参考谱列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取列表失败: {str(e)}'
        })


@maldi_matching_bp.route('/api/maldi/reference/<int:ref_id>', methods=['DELETE'])
def delete_reference(ref_id):
    """
    删除参考谱

    Response:
        {
            "success": true,
            "message": "删除成功"
        }
    """
    try:
        reference = MaldiReference.query.get(ref_id)

        if not reference:
            return jsonify({
                'success': False,
                'message': f'参考谱 ID {ref_id} 不存在'
            })

        db.session.delete(reference)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '删除成功'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"删除参考谱失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'删除失败: {str(e)}'
        })


@maldi_matching_bp.route('/api/maldi/strains', methods=['GET'])
def get_strains():
    """
    获取所有菌种列表（用于添加参考谱时选择）

    Response:
        {
            "success": true,
            "strains": [
                {
                    "id": int,
                    "name": str,
                    "scientific_name": str
                },
                ...
            ]
        }
    """
    try:
        strains = Strain.query.filter(Strain.is_active == True).order_by(Strain.name).all()

        return jsonify({
            'success': True,
            'strains': [
                {
                    'id': s.id,
                    'name': s.name or '',
                    'scientific_name': s.scientific_name or ''
                }
                for s in strains
            ]
        })

    except Exception as e:
        current_app.logger.error(f"获取菌种列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取菌种列表失败: {str(e)}'
        })


@maldi_matching_bp.route('/api/16s/match', methods=['POST'])
def match_16s():
    """
    16S RNA 序列匹配接口

    Request:
        - sequence: 16S 序列文本（form data 或 JSON）
        - top_k: 返回前K个结果（可选，默认5）

    Response:
        {
            "success": true,
            "candidates": [
                {
                    "strain_id": int,
                    "strain_name": str,
                    "scientific_name": str,
                    "similarity": float,  # 相似度 0-1
                    "match_length": int,  # 匹配长度
                    "query_length": int,  # 查询序列长度
                    "ref_length": int     # 参考序列长度
                },
                ...
            ],
            "query_info": {
                "length": int,
                "preview": str  # 前50个字符预览
            }
        }
    """
    try:
        # 获取序列数据
        if request.is_json:
            data = request.get_json()
            sequence = data.get('sequence', '')
        else:
            sequence = request.form.get('sequence', '')

        # 清理序列（移除空白字符、换行符）
        sequence = ''.join(sequence.split()).upper()

        if not sequence:
            return jsonify({
                'success': False,
                'message': '请输入 16S RNA 序列'
            })

        if len(sequence) < 50:
            return jsonify({
                'success': False,
                'message': '序列长度过短（至少需要50个碱基）'
            })

        # 获取参数
        top_k = int(request.form.get('top_k', 5) if not request.is_json else request.get_json().get('top_k', 5))

        # 查询所有 16S 参考序列
        references = Strain16S.query.join(Strain).filter(
            Strain.is_active == True,
            Strain16S.strain_16s.isnot(None),
            Strain16S.strain_16s != ''
        ).all()

        if not references:
            return jsonify({
                'success': False,
                'message': '16S 参考库为空，请先添加参考序列'
            })

        # 计算相似度
        candidates = []
        for ref in references:
            ref_sequence = ''.join(ref.strain_16s.split()).upper()

            # 使用 SequenceMatcher 计算相似度
            matcher = SequenceMatcher(None, sequence, ref_sequence)
            similarity = matcher.ratio()

            # 获取最长匹配块
            match = matcher.find_longest_match(0, len(sequence), 0, len(ref_sequence))

            candidates.append({
                'strain_id': ref.strain_id,
                'strain_name': ref.strain.name or '未知菌种',
                'scientific_name': ref.strain.scientific_name or '-',
                'similarity': similarity,
                'match_length': match.size,
                'query_length': len(sequence),
                'ref_length': len(ref_sequence),
                'reference_id': ref.id
            })

        # 按相似度排序
        candidates.sort(key=lambda x: x['similarity'], reverse=True)

        # 返回 Top-K
        top_candidates = candidates[:top_k]

        if not top_candidates:
            return jsonify({
                'success': False,
                'message': '未找到匹配的参考序列'
            })

        return jsonify({
            'success': True,
            'candidates': top_candidates,
            'query_info': {
                'length': len(sequence),
                'preview': sequence[:50] + ('...' if len(sequence) > 50 else '')
            }
        })

    except Exception as e:
        current_app.logger.error(f"16S 匹配失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'匹配失败: {str(e)}'
        })
