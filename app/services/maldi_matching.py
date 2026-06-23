"""
MALDI-TOF 质谱匹配服务

核心功能：
- 解析 MALDI-TOF TXT 文件
- 峰归一化
- 质谱匹配算法（余弦相似度、峰覆盖率、综合打分）
"""

from __future__ import annotations

import numpy as np
from typing import List, Tuple, Dict, Optional
import tempfile
import os


def parse_maldi_txt_from_bytes(file_bytes: bytes) -> Dict:
    """
    从字节流解析 MALDI-TOF TXT 文件

    文件格式：
    - 注释行以 # 开头
    - COM= 行包含样本ID
    - 数据行：两列，m/z 和 intensity

    Args:
        file_bytes: 文件字节流

    Returns:
        dict: {
            'sample_id': str or None,
            'peaks': List[[mz, intensity], ...],
            'peak_count': int
        }
    """
    sample_id = None
    peaks = []

    # 尝试多种编码
    content = None
    for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
        try:
            content = file_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        # 所有编码都失败，使用 utf-8 并忽略错误
        content = file_bytes.decode('utf-8', errors='ignore')

    lines = content.split('\n')

    for line in lines:
        line = line.strip()

        # 跳过空行
        if not line:
            continue

        # 跳过注释行
        if line.startswith('#'):
            continue

        # 解析 COM= 行（样本ID）
        if line.startswith('COM='):
            sample_id = line[4:].strip()
            continue

        # 解析数据行
        parts = line.split()
        if len(parts) >= 2:
            try:
                mz = float(parts[0])
                intensity = float(parts[1])
                peaks.append([mz, intensity])
            except (ValueError, IndexError):
                continue

    return {
        'sample_id': sample_id,
        'peaks': peaks,
        'peak_count': len(peaks)
    }


def normalize_peaks(peaks: List[List[float]]) -> List[List[float]]:
    """
    峰强度归一化到 [0, 1]

    Args:
        peaks: [[mz1, intensity1], [mz2, intensity2], ...]

    Returns:
        归一化后的峰列表
    """
    if not peaks:
        return []

    # 提取强度值
    intensities = [p[1] for p in peaks]
    max_intensity = max(intensities)

    if max_intensity == 0:
        return peaks

    # 归一化
    return [[p[0], p[1] / max_intensity] for p in peaks]


def cosine_similarity(query_peaks: List[List[float]], ref_peaks: List[List[float]], mz_tolerance: float = 0.5) -> float:
    """
    计算余弦相似度（先对齐m/z）

    Args:
        query_peaks: 查询峰列表 [[mz, intensity], ...]
        ref_peaks: 参考峰列表 [[mz, intensity], ...]
        mz_tolerance: m/z 容差（Da）

    Returns:
        余弦相似度 [0, 1]
    """
    if not query_peaks or not ref_peaks:
        return 0.0

    # 收集所有的 m/z 值
    all_mz = set()
    for mz, _ in query_peaks:
        all_mz.add(round(mz))  # 四舍五入到整数
    for mz, _ in ref_peaks:
        all_mz.add(round(mz))

    if not all_mz:
        return 0.0

    # 创建 m/z 网格（排序）
    mz_grid = sorted(all_mz)

    # 将峰映射到网格上
    query_vec = np.zeros(len(mz_grid))
    ref_vec = np.zeros(len(mz_grid))

    # 填充查询向量
    for q_mz, q_int in query_peaks:
        # 找到最近的网格点
        closest_idx = min(range(len(mz_grid)), key=lambda i: abs(mz_grid[i] - q_mz))
        if abs(mz_grid[closest_idx] - q_mz) <= mz_tolerance:
            query_vec[closest_idx] = max(query_vec[closest_idx], q_int)  # 取最大值

    # 填充参考向量
    for r_mz, r_int in ref_peaks:
        # 找到最近的网格点
        closest_idx = min(range(len(mz_grid)), key=lambda i: abs(mz_grid[i] - r_mz))
        if abs(mz_grid[closest_idx] - r_mz) <= mz_tolerance:
            ref_vec[closest_idx] = max(ref_vec[closest_idx], r_int)  # 取最大值

    # 计算余弦相似度
    dot_product = np.dot(query_vec, ref_vec)
    norm_query = np.linalg.norm(query_vec)
    norm_ref = np.linalg.norm(ref_vec)

    if norm_query == 0 or norm_ref == 0:
        return 0.0

    return float(dot_product / (norm_query * norm_ref))


def match_peaks(
    query_peaks: List[List[float]],
    ref_peaks: List[List[float]],
    mz_tolerance: float = 0.5
) -> Dict:
    """
    峰匹配算法

    Args:
        query_peaks: 查询峰列表（已归一化）
        ref_peaks: 参考峰列表（已归一化）
        mz_tolerance: m/z 容差（Da），默认 ±0.5

    Returns:
        dict: {
            'score': 综合分数,
            'cosine_sim': 余弦相似度,
            'query_coverage': 查询峰覆盖率,
            'ref_coverage': 参考峰覆盖率,
            'matched_count': 匹配峰数量
        }
    """
    if not query_peaks or not ref_peaks:
        return {
            'score': 0.0,
            'cosine_sim': 0.0,
            'query_coverage': 0.0,
            'ref_coverage': 0.0,
            'matched_count': 0
        }

    matched_query = []
    matched_ref = []

    # m/z 容差匹配
    for q_mz, q_int in query_peaks:
        for r_mz, r_int in ref_peaks:
            if abs(q_mz - r_mz) <= mz_tolerance:
                matched_query.append([q_mz, q_int])
                matched_ref.append([r_mz, r_int])
                break

    # 计算覆盖率
    query_coverage = len(matched_query) / len(query_peaks) if query_peaks else 0.0
    ref_coverage = len(matched_ref) / len(ref_peaks) if ref_peaks else 0.0

    # 计算余弦相似度（使用对齐的m/z）
    cosine_sim = cosine_similarity(query_peaks, ref_peaks, mz_tolerance)

    # 综合打分（可调权重）
    # cosine_sim: 0.5, query_coverage: 0.3, ref_coverage: 0.2
    final_score = 0.5 * cosine_sim + 0.3 * query_coverage + 0.2 * ref_coverage

    return {
        'score': float(np.clip(final_score, 0.0, 1.0)),
        'cosine_sim': float(cosine_sim),
        'query_coverage': float(query_coverage),
        'ref_coverage': float(ref_coverage),
        'matched_count': len(matched_query)
    }


def filter_peaks_by_intensity(peaks: List[List[float]], min_intensity_ratio: float = 0.01) -> List[List[float]]:
    """
    过滤低强度峰

    Args:
        peaks: [[mz, intensity], ...] （已归一化）
        min_intensity_ratio: 最小强度阈值（相对于最大强度的比例）

    Returns:
        过滤后的峰列表
    """
    if not peaks:
        return []

    # 过滤
    return [p for p in peaks if p[1] >= min_intensity_ratio]


def match_query_against_references(
    query_peaks: List[List[float]],
    references: List,
    mz_tolerance: float = 0.5,
    min_intensity_ratio: float = 0.01,
    top_k: int = 3
) -> List[Dict]:
    """
    将查询峰与所有参考谱匹配并返回 Top-K

    Args:
        query_peaks: 查询峰列表（原始未归一化）
        references: 参考谱对象列表（MaldiReference）
        mz_tolerance: m/z 容差
        min_intensity_ratio: 最小强度阈值
        top_k: 返回前K个结果

    Returns:
        List[dict]: Top-K 匹配结果
    """
    if not query_peaks or not references:
        return []

    # 归一化查询峰
    normalized_query = normalize_peaks(query_peaks)

    # 过滤低强度峰
    filtered_query = filter_peaks_by_intensity(normalized_query, min_intensity_ratio)

    if not filtered_query:
        return []

    results = []

    for ref in references:
        # 提取参考峰并归一化
        ref_peaks = ref.peaks  # JSON 格式: [[mz, intensity], ...]

        if not ref_peaks:
            continue

        normalized_ref = normalize_peaks(ref_peaks)
        filtered_ref = filter_peaks_by_intensity(normalized_ref, min_intensity_ratio)

        if not filtered_ref:
            continue

        # 匹配
        match_result = match_peaks(filtered_query, filtered_ref, mz_tolerance)

        results.append({
            'reference_id': ref.id,
            'strain_id': ref.strain_id,
            'strain_name': ref.strain.name if ref.strain else None,
            'scientific_name': ref.strain.scientific_name if ref.strain else None,
            'sample_id': ref.sample_id,
            'score': match_result['score'],
            'cosine_sim': match_result['cosine_sim'],
            'query_coverage': match_result['query_coverage'],
            'ref_coverage': match_result['ref_coverage'],
            'matched_count': match_result['matched_count']
        })

    # 按综合分数降序排序
    results.sort(key=lambda x: x['score'], reverse=True)

    # 返回 Top-K
    return results[:top_k]
