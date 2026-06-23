"""
测试质谱图生成

用于验证 matplotlib 和图表生成功能是否正常
"""

from app.services.spectrum_plot import generate_comparison_plot, generate_single_plot
import sys

# 测试数据
test_query_peaks = [
    [3070.69, 0.423],
    [3124.91, 0.431],
    [3186.31, 1.223],
    [4000.0, 0.8],
    [5000.0, 0.6]
]

test_ref_peaks = [
    [3070.0, 0.5],
    [3125.0, 0.6],
    [3186.0, 1.0],
    [4000.0, 0.7],
    [5000.0, 0.5]
]

print("开始测试质谱图生成...")

try:
    # 测试对比图
    print("生成对比图...")
    plot_base64 = generate_comparison_plot(
        query_peaks=test_query_peaks,
        ref_peaks=test_ref_peaks,
        query_sample_id="测试样本",
        ref_sample_id="参考样本",
        ref_strain_name="测试菌种"
    )

    if plot_base64:
        print(f"[OK] 对比图生成成功！")
        print(f"  Base64 长度: {len(plot_base64)} 字符")
        print(f"  前100个字符: {plot_base64[:100]}")
    else:
        print("[FAIL] 对比图生成失败：返回空值")
        sys.exit(1)

    # 测试单独图
    print("\n生成单独图...")
    single_plot = generate_single_plot(
        peaks=test_query_peaks,
        sample_id="测试样本",
        color='gray'
    )

    if single_plot:
        print(f"[OK] 单独图生成成功！")
        print(f"  Base64 长度: {len(single_plot)} 字符")
    else:
        print("[FAIL] 单独图生成失败：返回空值")
        sys.exit(1)

    print("\n[OK] 所有测试通过！")

except Exception as e:
    print(f"\n[FAIL] 测试失败：{str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
