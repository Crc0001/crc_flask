"""
质谱图生成服务

生成 MALDI-TOF 质谱对比图：
- 红色线：参考谱
- 灰色线：查询样本
"""

import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from io import BytesIO
import base64
from typing import List, Tuple
from scipy.signal import savgol_filter
from scipy.ndimage import gaussian_filter1d, minimum_filter1d

# 设置中文字体
try:
    # 尝试使用系统字体
    plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
except:
    pass


def process_spectrum(mz: np.ndarray, intensity: np.ndarray) -> np.ndarray:
    """
    按照 MALDIquant 方法处理质谱数据

    步骤：
    1. Savitzky-Golay 平滑
    2. 去除基线
    3. 再次轻微平滑

    Args:
        mz: m/z 数组
        intensity: 强度数组

    Returns:
        处理后的强度数组
    """
    if len(mz) < 10:
        return intensity

    # 步骤1: Savitzky-Golay 平滑
    # window_length 必须是奇数，根据数据点数自适应
    window_length = min(21, len(mz) if len(mz) % 2 == 1 else len(mz) - 1)
    if window_length >= 3:
        try:
            intensity_smooth = savgol_filter(intensity, window_length, polyorder=3)
        except:
            intensity_smooth = intensity
    else:
        intensity_smooth = intensity

    # 步骤2: 去除基线
    # 用最小值滤波估计基线
    baseline_size = min(50, len(mz) // 10)
    try:
        baseline_estimated = minimum_filter1d(intensity_smooth, size=baseline_size)
        intensity_corrected = intensity_smooth - baseline_estimated
        intensity_corrected = np.maximum(intensity_corrected, 0)  # 确保非负
    except:
        intensity_corrected = intensity_smooth

    # 步骤3: 再次轻微平滑
    try:
        intensity_final = gaussian_filter1d(intensity_corrected, sigma=1)
    except:
        intensity_final = intensity_corrected

    return intensity_final


def generate_comparison_plot(
    query_peaks: List[List[float]],
    ref_peaks: List[List[float]],
    query_sample_id: str = None,
    ref_sample_id: str = None,
    ref_strain_name: str = None
) -> str:
    """
    生成质谱对比图（平滑填充峰形）

    Args:
        query_peaks: 查询峰数据 [[mz, intensity], ...]
        ref_peaks: 参考峰数据 [[mz, intensity], ...]
        query_sample_id: 查询样本ID
        ref_sample_id: 参考样本ID
        ref_strain_name: 参考菌种名称

    Returns:
        base64 编码的图片数据
    """
    # 创建图表
    fig, ax = plt.subplots(figsize=(14, 6))

    # 提取 m/z 和 intensity（转换为 numpy 数组）
    query_mz = np.array([p[0] for p in query_peaks])
    query_int = np.array([p[1] for p in query_peaks])

    ref_mz = np.array([p[0] for p in ref_peaks])
    ref_int = np.array([p[1] for p in ref_peaks])

    # 归一化强度到 [0, 1]（如果还没归一化）
    if len(query_int) > 0 and query_int.max() > 0:
        query_int = query_int / query_int.max()

    if len(ref_int) > 0 and ref_int.max() > 0:
        ref_int = ref_int / ref_int.max()

    # 使用 MALDIquant 方法处理质谱数据
    query_smooth = process_spectrum(query_mz, query_int)
    ref_smooth = process_spectrum(ref_mz, ref_int)

    # 绘制查询样本（灰色填充）
    ax.fill_between(query_mz, 0, query_smooth, color='gray', alpha=0.3, label='查询样本')
    ax.plot(query_mz, query_smooth, color='dimgray', linewidth=0.8, alpha=0.8)

    # 绘制参考谱（红色填充）
    ax.fill_between(ref_mz, 0, ref_smooth, color='crimson', alpha=0.3, label='参考谱')
    ax.plot(ref_mz, ref_smooth, color='darkred', linewidth=1, alpha=0.9)

    # 设置标签和标题
    ax.set_xlabel('m/z', fontsize=12)
    ax.set_ylabel('归一化强度', fontsize=12)

    title = 'MALDI-TOF 质谱对比'
    if ref_strain_name:
        title += f' - {ref_strain_name}'
    ax.set_title(title, fontsize=14, fontweight='bold')

    # 添加图例
    ax.legend(loc='upper right')

    # 设置网格
    ax.grid(True, alpha=0.3, axis='y')

    # 设置 x 轴范围固定为 3000-20000（质荷比范围）
    ax.set_xlim(3000, 20000)

    # 自适应 y 轴
    all_smooth = np.concatenate([query_smooth, ref_smooth])
    if len(all_smooth) > 0 and all_smooth.max() > 0:
        ax.set_ylim(0, all_smooth.max() * 1.1)

    # 去掉顶部和右边框
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # 调整布局
    plt.tight_layout()

    # 保存到字节流
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)

    # 转换为 base64
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')

    # 关闭图表
    plt.close(fig)

    return img_base64


def generate_single_plot(
    peaks: List[List[float]],
    sample_id: str = None,
    color: str = 'gray',
    title: str = '质谱图'
) -> str:
    """
    生成单个质谱图（平滑填充峰形）

    Args:
        peaks: 峰数据 [[mz, intensity], ...]
        sample_id: 样本ID
        color: 线条颜色
        title: 图表标题

    Returns:
        base64 编码的图片数据
    """
    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 6))

    # 提取 m/z 和 intensity（转换为 numpy 数组）
    mz = np.array([p[0] for p in peaks])
    intensity = np.array([p[1] for p in peaks])

    # 归一化强度
    if len(intensity) > 0 and intensity.max() > 0:
        intensity = intensity / intensity.max()

    # 使用 MALDIquant 方法处理质谱数据
    smooth_int = process_spectrum(mz, intensity)

    # 绘制填充区域和线条
    ax.fill_between(mz, 0, smooth_int, color=color, alpha=0.3)
    ax.plot(mz, smooth_int, color=color, linewidth=1, alpha=0.9)

    # 设置标签和标题
    ax.set_xlabel('m/z', fontsize=12)
    ax.set_ylabel('归一化强度', fontsize=12)

    if sample_id:
        title += f' - {sample_id}'
    ax.set_title(title, fontsize=14, fontweight='bold')

    # 设置网格
    ax.grid(True, alpha=0.3)

    # 设置 x 轴范围固定为 3000-20000（质荷比范围）
    ax.set_xlim(3000, 20000)

    # 自适应 y 轴
    if len(smooth_int) > 0 and smooth_int.max() > 0:
        ax.set_ylim(0, smooth_int.max() * 1.1)

    # 去掉顶部和右边框
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # 调整布局
    plt.tight_layout()

    # 保存到字节流
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)

    # 转换为 base64
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')

    # 关闭图表
    plt.close(fig)

    return img_base64
