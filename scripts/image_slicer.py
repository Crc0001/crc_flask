# -*- coding: utf-8 -*-
"""
图像切片工具 v3 — 纯图片切片（递归 + 原地输出）
对大图按固定尺寸滑动窗口切片，支持重叠、边缘填充、中文路径。
GUI + CLI 双模式。
新增: --recursive 递归子目录, --inplace 原地输出
"""

import os
import cv2
import numpy as np
import glob
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import argparse
from datetime import datetime


# ──────────────────────────────────────────────
#  图片查找
# ──────────────────────────────────────────────
EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')


def check_content(gray_img, min_std=18, min_edges=0.001):
    """
    内容检测：排除空白培养基 tile。
    - min_std:  灰度标准差阈值，低于此值视为空白
    - min_edges: Canny边缘占比阈值，低于此值视为空白
    返回 True 表示有内容（保留），False 表示空白（丢弃）。
    """
    std = float(np.std(gray_img))
    if std < min_std:
        return False
    edges = cv2.Canny(gray_img, 50, 150)
    edge_ratio = float(np.sum(edges > 0)) / edges.size
    if edge_ratio < min_edges:
        return False
    return True


def find_images(root_dir, recursive=True):
    """递归查找所有图片，返回路径列表"""
    if recursive:
        paths = []
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith('sliced_')]
            for f in filenames:
                if f.lower().endswith(EXTENSIONS) and '__tile' not in f:
                    paths.append(os.path.join(dirpath, f))
        return sorted(paths)
    else:
        paths = []
        for ext in ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG',
                     '*.bmp', '*.BMP', '*.tif', '*.tiff', '*.TIF', '*.TIFF'):
            paths.extend(glob.glob(os.path.join(root_dir, ext)))
        return sorted(set(paths))


# ──────────────────────────────────────────────
#  核心切片逻辑
# ──────────────────────────────────────────────
def slice_images(input_dir, output_dir=None, slice_size=1024, overlap_ratio=0.2,
                 recursive=False, inplace=False, exclude_tiles=None,
                 min_std=18, min_edges=0.001, status_callback=None):
    """
    参数
    ----
    input_dir :        输入根目录
    output_dir :       输出根目录（inplace 模式下忽略）
    slice_size :       切片边长
    overlap_ratio :    重叠比例
    recursive :        是否递归子目录
    inplace :          是否原地输出（切片与原始图片同目录）
    status_callback :  GUI 回调
    """
    img_paths = find_images(input_dir, recursive=recursive)
    exclude_set = parse_exclude(exclude_tiles) if exclude_tiles else set()

    if not img_paths:
        msg = f"错误：在 {input_dir} 中没有找到图片"
        report(msg, status_callback)
        return

    stride = int(slice_size * (1 - overlap_ratio))
    if stride < 1:
        stride = 1

    # 输出目录策略
    if inplace:
        out_root = input_dir  # 原地：tile 写回每个图片所在子目录
    elif output_dir:
        out_root = output_dir
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_root = os.path.join(input_dir, f"sliced_{ts}")

    if not inplace:
        os.makedirs(out_root, exist_ok=True)

    total_tiles = 0
    total_skipped = 0
    total_blank = 0
    total_excluded = 0

    report(f"输入目录: {input_dir}", status_callback)
    report(f"模式: {'原地输出' if inplace else '输出到 ' + out_root}", status_callback)
    report(f"递归: {'是' if recursive else '否'}, 内容过滤: std>{min_std} edges>{min_edges}", status_callback)
    report(f"切片大小: {slice_size} px, 重叠: {overlap_ratio}, 步长: {stride} px", status_callback)
    report(f"找到 {len(img_paths)} 张图片，开始切片...\n", status_callback)

    for idx, img_path in enumerate(img_paths, 1):
        raw = np.fromfile(img_path, dtype=np.uint8)
        img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if img is None:
            report(f"  [{idx}/{len(img_paths)}] ⚠ 跳过无法读取", status_callback)
            total_skipped += 1
            continue

        h, w = img.shape[:2]
        base_name = os.path.splitext(os.path.basename(img_path))[0]

        # 确定输出目录
        if inplace:
            tile_dir = os.path.dirname(img_path)  # 和原图同目录
        else:
            tile_dir = out_root
        os.makedirs(tile_dir, exist_ok=True)

        # 滑动窗口
        tile_idx = 0
        blank_count = 0
        for y in range(0, h, stride):
            for x in range(0, w, stride):
                y1, y2 = y, min(y + slice_size, h)
                x1, x2 = x, min(x + slice_size, w)
                tile = img[y1:y2, x1:x2]
                th, tw = tile.shape[:2]

                if th < slice_size or tw < slice_size:
                    padded = cv2.copyMakeBorder(
                        tile, 0, slice_size - th, 0, slice_size - tw,
                        cv2.BORDER_CONSTANT, value=(0, 0, 0))
                else:
                    padded = tile

                tile_idx += 1

                # 定向排除
                if exclude_set and (tile_idx - 1) in exclude_set:
                    total_excluded += 1
                    continue

                # 内容检测：筛空白
                gray = cv2.cvtColor(padded, cv2.COLOR_BGR2GRAY)
                if not check_content(gray, min_std, min_edges):
                    blank_count += 1
                    total_blank += 1
                    continue

                out_name = f"{base_name}__tile{tile_idx:04d}.jpg"
                out_path = os.path.join(tile_dir, out_name)
                _, enc = cv2.imencode('.jpg', padded, [cv2.IMWRITE_JPEG_QUALITY, 95])
                enc.tofile(out_path)

                total_tiles += 1

        if idx % 50 == 0 or idx == len(img_paths):
            kept = tile_idx - len(exclude_set & set(range(tile_idx))) - blank_count
            parts = [f'{kept} tiles']
            excl = len(exclude_set & set(range(tile_idx)))
            if excl: parts.append(f'excl {excl}')
            if blank_count: parts.append(f'blank {blank_count}')
            report(f"  [{idx}/{len(img_paths)}] {base_name}: {w}x{h} → {' '.join(parts)}", status_callback)

    report(f"\n{'='*50}", status_callback)
    report(f"完成！处理 {len(img_paths) - total_skipped} 张图片，生成 {total_tiles} 个切片", status_callback)
    if total_excluded:
        report(f"定向排除 {total_excluded} 个", status_callback)
    if total_blank:
        report(f"空白过滤 {total_blank} 个", status_callback)
    if total_skipped:
        report(f"跳过 {total_skipped} 张", status_callback)

    return out_root


def parse_exclude(s):
    """解析排除 tile 索引, 如 '3,7,11,15-19' → {3,7,11,15,16,17,18,19}"""
    result = set()
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            result.update(range(int(a), int(b) + 1))
        elif part:
            result.add(int(part))
    return result


def report(msg, callback=None):
    print(msg)
    if callback:
        callback(msg)


# ──────────────────────────────────────────────
#  GUI（Tkinter）
# ──────────────────────────────────────────────
class SlicerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图像切片工具 v3")
        self.geometry("660x480")
        self.resizable(False, False)
        self.processing = False
        self._build_ui()

    def _build_ui(self):
        f = ttk.Frame(self, padding="12")
        f.grid(row=0, column=0, sticky="nsew")

        row = 0
        ttk.Label(f, text="输入目录：").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.var_in = tk.StringVar(value="")
        ttk.Entry(f, textvariable=self.var_in, width=52).grid(row=row, column=1, sticky=tk.EW, pady=4)
        ttk.Button(f, text="浏览", command=lambda: self._browse(self.var_in)).grid(row=row, column=2, padx=4)

        row += 1
        ttk.Label(f, text="输出目录：").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.var_out = tk.StringVar(value="")
        ttk.Entry(f, textvariable=self.var_out, width=52).grid(row=row, column=1, sticky=tk.EW, pady=4)
        ttk.Button(f, text="浏览", command=lambda: self._browse(self.var_out)).grid(row=row, column=2, padx=4)

        row += 1
        ttk.Label(f, text="切片大小 (px)：").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.var_size = tk.IntVar(value=224)
        ttk.Entry(f, textvariable=self.var_size, width=10).grid(row=row, column=1, sticky=tk.W)

        row += 1
        ttk.Label(f, text="重叠比例 (0~0.5)：").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.var_overlap = tk.DoubleVar(value=0.2)
        ttk.Entry(f, textvariable=self.var_overlap, width=10).grid(row=row, column=1, sticky=tk.W)

        row += 1
        self.var_recurse = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="递归子目录", variable=self.var_recurse).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        self.var_inplace = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="原地输出（切片与原始图放在同一目录）", variable=self.var_inplace).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(f, text="运行日志：").grid(row=row, column=0, sticky=tk.NW, pady=4)
        self.txt_log = tk.Text(f, height=10, width=62, state='disabled', bg='#1e1e1e', fg='#d4d4d4',
                               insertbackground='white')
        self.txt_log.grid(row=row, column=1, columnspan=2, pady=4, sticky=tk.W)

        row += 1
        self.btn = ttk.Button(f, text="▶  开 始 切 片", command=self._start)
        self.btn.grid(row=row, column=0, columnspan=3, pady=8)

    def _browse(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~/Desktop"))
        if d:
            var.set(d)

    def _log(self, msg):
        self.txt_log.config(state='normal')
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state='disabled')
        self.update_idletasks()

    def _start(self):
        if self.processing:
            messagebox.showwarning("提示", "切片正在进行中")
            return

        inp = self.var_in.get().strip()
        out = self.var_out.get().strip()
        size = self.var_size.get()
        overlap = self.var_overlap.get()
        recurse = self.var_recurse.get()
        inplace = self.var_inplace.get()

        if not inp or not os.path.isdir(inp):
            messagebox.showerror("错误", "请选择有效的输入目录")
            return
        if not inplace and not out:
            out = inp
        if size < 64:
            messagebox.showerror("错误", "切片大小至少 64 px")
            return
        if not (0 <= overlap <= 0.5):
            messagebox.showerror("错误", "重叠比例应在 0~0.5 之间")
            return

        if inplace:
            if not messagebox.askyesno("确认", f"切片将直接写入原图所在目录，确认？"):
                return

        self.processing = True
        self.btn.config(state='disabled')
        self._log("=" * 50)

        def worker():
            try:
                slice_images(inp, out, size, overlap,
                             recursive=recurse, inplace=inplace,
                             status_callback=self._log)
            except Exception as e:
                self._log(f"❌ 切片失败：{e}")
                import traceback
                traceback.print_exc()
            finally:
                self.processing = False
                self.btn.config(state='normal')

        threading.Thread(target=worker, daemon=True).start()


# ──────────────────────────────────────────────
#  入口
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="图像切片工具 v3 — 将大图切成固定大小的 tile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python image_slicer.py -i ./test_split -s 224 --recursive --inplace
  python image_slicer.py -i ./test_split -o ./output -s 1024 -r 0.2
  python image_slicer.py --gui
        """)
    parser.add_argument('-i', '--input_dir', type=str, help='输入目录')
    parser.add_argument('-o', '--output_dir', type=str, default=None, help='输出目录')
    parser.add_argument('-s', '--slice_size', type=int, default=224, help='切片大小 px (默认 224)')
    parser.add_argument('-r', '--overlap_ratio', type=float, default=0.2, help='重叠比例 (默认 0.2)')
    parser.add_argument('--recursive', action='store_true', help='递归子目录')
    parser.add_argument('--inplace', action='store_true', help='原地输出（切片写入原图所在目录）')
    parser.add_argument('--exclude_tiles', type=str, default=None,
                        help='排除的切片索引, 如 "3,7,11,15-19"')
    parser.add_argument('--min_std', type=float, default=18,
                        help='内容检测: 灰度标准差阈值 (默认 18, 低于此值视为空白)')
    parser.add_argument('--min_edges', type=float, default=0.001,
                        help='内容检测: Canny边缘占比阈值 (默认 0.001)')
    parser.add_argument('--no_filter', action='store_true',
                        help='关闭内容过滤（保留所有切片包括空白）')
    parser.add_argument('--gui', action='store_true', help='启动 GUI')

    args = parser.parse_args()

    if args.gui or (not args.input_dir):
        app = SlicerApp()
        app.mainloop()
    else:
        out = args.output_dir
        mstd, medge = (0, 0) if args.no_filter else (args.min_std, args.min_edges)
        slice_images(args.input_dir, out, args.slice_size, args.overlap_ratio,
                     recursive=args.recursive, inplace=args.inplace,
                     exclude_tiles=args.exclude_tiles,
                     min_std=mstd, min_edges=medge)


if __name__ == "__main__":
    main()
