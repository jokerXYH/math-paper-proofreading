# -*- coding: utf-8 -*-
"""数学试卷 PDF 识别器（对 PDF 友好）
====================================================
功能：
  1) 逐页提取文本层（text.txt）
  2) 逐页渲染 PNG（pages/page_XX.png）——公式/图形必须看图核对
  3) 自动切分题号（questions.json）——初切，人工复核
  4) 检测无文本层页面（扫描版），提示走 OCR
  5) 任意区域高DPI裁剪（--crop 页码:x0,y0,x1,y1:备注）

用法：
  python extract_pdf.py 试卷.pdf -o 输出目录 --dpi 160
  python extract_pdf.py 试卷.pdf --crop 8:163,332,316,475:图2 --crop 1:470,740,552,770:正数x
  # --crop 可单独使用（不产出整页图时加 --no-pages）

依赖：pymupdf（pip install pymupdf）
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

Q_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]\s*")
PART_RE = re.compile(r"^\s*[（(](\d{1,2})[）)]")


def crop(page, rect, out_path, dpi=300):
    pix = page.get_pixmap(dpi=dpi, clip=pymupdf.Rect(*rect))
    pix.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="数学试卷PDF识别器")
    ap.add_argument("pdf", help="PDF 路径")
    ap.add_argument("-o", "--out", default="pdf_extract", help="输出目录")
    ap.add_argument("--dpi", type=int, default=160, help="整页渲染DPI（默认160）")
    ap.add_argument("--crop", action="append", default=[],
                    help="局部裁剪 页码:x0,y0,x1,y1:备注（可重复）")
    ap.add_argument("--no-pages", action="store_true", help="不渲染整页图")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    os.makedirs(args.out, exist_ok=True)
    pages_dir = os.path.join(args.out, "pages")
    if not args.no_pages:
        os.makedirs(pages_dir, exist_ok=True)

    all_text, questions, no_text_pages, summary = [], [], [], []
    for i, page in enumerate(doc):
        t = page.get_text()
        stripped = re.sub(r"\s", "", t)
        if len(stripped) < 40 and not args.no_pages:
            no_text_pages.append(i + 1)
        all_text.append(f"===== 第{i+1}页 =====\n{t}")
        summary.append((i + 1, len(t), len(page.get_images())))
        if not args.no_pages:
            pix = page.get_pixmap(dpi=args.dpi)
            pix.save(os.path.join(pages_dir, f"page_{i+1:02d}.png"))
        for line in t.splitlines():
            ls = line.strip()
            m = Q_RE.match(ls)
            if m:
                q = {"qno": int(m.group(1)), "page": i + 1,
                     "first_line": ls[:90]}
                mp = PART_RE.match(re.sub(r"^\s*\d{1,3}\s*[.．、]\s*", "", ls))
                if mp:
                    q["part"] = int(mp.group(1))
                questions.append(q)

    with open(os.path.join(args.out, "text.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(all_text))
    with open(os.path.join(args.out, "questions.json"), "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=1)

    # 题号序列诊断
    qnos = [q["qno"] for q in questions]
    warns = []
    for a, b in zip(qnos, qnos[1:]):
        if b == a:
            warns.append(f"题号重复: {a}")
        elif b < a and b != 1:
            warns.append(f"题号回退: {a} -> {b}（检查是否跨题型重新编号或编号错乱）")

    # 裁剪任务
    crop_list = []
    for spec in args.crop:
        try:
            pno_s, rect_s, *name_s = spec.split(":")
            pno = int(pno_s)
            rect = [float(v) for v in rect_s.split(",")]
            name = name_s[0] if name_s else f"crop_p{pno}"
            out = os.path.join(args.out, f"crop_{name}.png")
            crop(doc[pno - 1], rect, out, dpi=350)
            crop_list.append(out)
        except Exception as e:  # noqa
            warns.append(f"裁剪失败 {spec}: {e}")

    report = []
    report.append(f"文件: {args.pdf}")
    report.append(f"页数: {len(doc)}")
    report.append(f"文本层: {'有' if len(no_text_pages) < len(doc) else '无'}")
    if no_text_pages:
        report.append(f"⚠ 无文本层页面(疑似扫描/图片)：{no_text_pages} → 需要OCR或看渲染图")
    report.append(f"检出题号条目: {len(questions)}（如 1,2,3,...,1,2,3 说明按题型重新编号）")
    if warns:
        report.append("题号诊断:")
        report.extend("  - " + w for w in warns)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\n".join(report))
    print(f"\n输出目录: {os.path.abspath(args.out)}")
    if crop_list:
        print("裁剪图:", *crop_list, sep="\n  ")


if __name__ == "__main__":
    main()
