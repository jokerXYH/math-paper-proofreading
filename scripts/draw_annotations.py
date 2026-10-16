# -*- coding: utf-8 -*-
"""试卷可视化批注引擎（红框 + 红字直接写进 PDF）
====================================================
把"错在哪 + 正确答案"画进 PDF 内容层（非浮层注释，任何阅读器/打印可见），
并渲染被标注页面为 PNG，便于检查与展示。

规格文件（JSON）：
{
  "marks": [
    {"page": 6, "rect": [31,43,53,64], "color": "red", "width": 1.6}
  ],
  "notes": [
    {"page": 1, "x": 60, "y": 795, "size": 8.5, "color": "red",
     "lines": ["▲第X题：...", "（可多行）"]},
    {"page": 5, "frame": [60,380,535,432], "x": 72, "y": 402,
     "size": 10, "color": "red", "lines": ["▲..."]}
  ]
}

用法：
  python draw_annotations.py --src 试卷.pdf --spec spec.json --dst 批注版.pdf
  python draw_annotations.py --src 试卷.pdf --spec spec.json --check-dir check/
  # 不传 --dst 时默认输出 原文件名（批注）.pdf

颜色: red / orange / blue / green / purple
坐标：PDF 点（pt），左上角为原点，A4 页面约 (0,0)-(595,842)。
"""
import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

COLORS = {
    "red": (0.85, 0.05, 0.05),
    "orange": (0.92, 0.42, 0.0),
    "blue": (0.0, 0.18, 0.8),
    "green": (0.0, 0.55, 0.1),
    "purple": (0.5, 0.0, 0.7),
}
FONT = "china-s"  # PyMuPDF 内置中文字体


def text_width(s, size):
    """真实字宽测量：优先用 PyMuPDF 字体度量（china-s 连 ASCII 也近似全角，
    纯启发式会低估导致批注被裁，这是踩过的坑）"""
    try:
        return pymupdf.get_text_length(s, fontname=FONT, fontsize=size)
    except Exception:
        w = 0.0
        for ch in s:
            if ch == " ":
                w += size * 0.5
            elif ord(ch) > 0x2E00:
                w += size
            else:
                w += size * 0.95
        return w


def wrap_line(s, size, max_width):
    """按真实字宽把一行折成多行（CJK 逐字折行）"""
    lines, cur = [], ""
    for ch in s:
        trial = cur + ch
        if text_width(trial, size) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser(description="试卷可视化批注引擎")
    ap.add_argument("--src", required=True, help="原始 PDF")
    ap.add_argument("--spec", required=True, help="批注规格 JSON")
    ap.add_argument("--dst", default=None, help="输出 PDF（默认 原名（批注）.pdf）")
    ap.add_argument("--check-dir", default=None, help="渲染被标注页 PNG 的目录")
    ap.add_argument("--dpi", type=int, default=130, help="检查图 DPI")
    args = ap.parse_args()

    doc = pymupdf.open(args.src)
    spec = json.load(open(args.spec, encoding="utf-8-sig"))
    warnings = []
    touched = set()

    # ---- 快照原始内容块（用于 P0-3 批注遮挡检测，必须在任何写入之前） ----
    orig_blocks = {}
    for nt in spec.get("notes", []):
        pno = int(nt["page"])
        if pno in orig_blocks:
            continue
        page = doc[pno - 1]
        blocks = [pymupdf.Rect(b[:4]) for b in page.get_text("blocks") if b[4].strip()]
        blocks += [pymupdf.Rect(im["bbox"]) for im in page.get_image_info()]
        orig_blocks[pno] = blocks

    for mk in spec.get("marks", []):
        pno = int(mk["page"])
        rect = pymupdf.Rect(*mk["rect"])
        color = COLORS.get(mk.get("color", "red"), COLORS["red"])
        doc[pno - 1].draw_rect(rect, color=color, width=mk.get("width", 1.6))
        touched.add(pno)

    for nt in spec.get("notes", []):
        pno = int(nt["page"])
        page = doc[pno - 1]
        color = COLORS.get(nt.get("color", "red"), COLORS["red"])
        size = nt.get("size", 9.5)
        x, y = float(nt["x"]), float(nt["y"])
        if "frame" in nt:
            page.draw_rect(pymupdf.Rect(*nt["frame"]), color=color, width=1.2)
        max_w = page.rect.width - x - 10
        final_lines = []
        for line in nt.get("lines", []):
            if nt.get("wrap", True) and text_width(line, size) > max_w:
                subs = wrap_line(line, size, max_w)
                warnings.append(
                    f"ℹ 第{pno}页批注自动折行（原行超宽 {text_width(line, size):.0f}pt > {max_w:.0f}pt）："
                    f"{line[:20]}... → {len(subs)} 行")
                final_lines.extend(subs)
            else:
                final_lines.append(line)
        step = size * 1.32
        if y + len(final_lines) * step > page.rect.height - 30:
            warnings.append(
                f"⚠ 第{pno}页批注共{len(final_lines)}行，从y={y:.0f}起写会超出页面底部，请上移或缩短！")
        # P0-3 遮挡检测：批注文字与原始正文/图形相交则告警
        if final_lines:
            line_w = max(text_width(l, size) for l in final_lines)
            note_rect = pymupdf.Rect(x, y - size * 0.9,
                                     x + line_w + 2,
                                     y + (len(final_lines) - 1) * step + size * 0.4)
            for blk in orig_blocks.get(pno, []):
                inter = blk & note_rect
                if not inter.is_empty and inter.width > 3 and inter.height > 3:
                    warnings.append(
                        f"⚠ 第{pno}页 批注与现有内容相交({inter.width:.0f}x{inter.height:.0f}pt)，建议移位："
                        f"{final_lines[0][:20]}...")
                    break
        for i, line in enumerate(final_lines):
            page.insert_text((x, y + i * step), line,
                             fontname=FONT, fontsize=size, color=color)
        touched.add(pno)

    dst = args.dst or os.path.splitext(args.src)[0] + "（批注）.pdf"
    doc.save(dst, deflate=True, garbage=3)
    print(f"已保存: {dst}")

    if warnings:
        print("\n".join(warnings))
    else:
        print("文字宽度检查: 全部通过 ✓")

    if args.check_dir:
        os.makedirs(args.check_dir, exist_ok=True)
        d2 = pymupdf.open(dst)
        for pno in sorted(touched):
            pix = d2[pno - 1].get_pixmap(dpi=args.dpi)
            out = os.path.join(args.check_dir, f"chk_{pno:02d}.png")
            pix.save(out)
            print("检查图:", out)
        print(f"共 {len(touched)} 页被标注 → 请逐张查看确认文字完整、无遮挡")


if __name__ == "__main__":
    main()
