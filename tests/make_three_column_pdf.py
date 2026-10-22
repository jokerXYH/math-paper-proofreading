# -*- coding: utf-8 -*-
"""生成三栏测试卷（验证 1–4 栏通用识别、跨栏不串、小数不误判题号）。

用法:
  python tests/make_three_column_pdf.py -o tests/out/_sample/three_column.pdf
"""
import argparse
import os

import pymupdf

# 三栏横版；每题尽量短，避免行宽超过栏宽
COLS = [
    [
        ("1．下列各数中最小的是（　　）", 10),
        ("A．-3　B．0　C．1　D．2", 10),
        ("2．计算 (-2)^3＝（　　）", 10),
        ("A．-8　B．-6　C．6　D．8", 10),
    ],
    [
        ("3．单项式 -3x²y 的系数是（　　）", 10),
        ("A．-3　B．3　C．-2　D．2", 10),
        ("4．数据 0.000007 用科学记数法", 10),
        ("表示为（　　）", 10),
        ("A．7×10⁻⁶　B．7×10⁻⁵", 10),
    ],
    [
        ("5．若 |x-2|=3，则 x＝（　　）", 10),
        ("A．5　B．-1　C．5或-1　D．1", 10),
        ("6．数列 1，4，9，16，…", 10),
        ("第 n 项为（　　）", 10),
        ("A．n²　B．2n", 10),
    ],
]


def build(out_path):
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)   # A4 横版
    page.insert_text((40, 55), "七年级数学三栏练习（技能自检样卷）",
                     fontsize=14, fontname="china-s")
    xs = [40, 300, 560]
    for ci, group in enumerate(COLS):
        y = 105
        for text, size in group:
            page.insert_text((xs[ci], y), text, fontsize=size, fontname="china-s")
            y += 22
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.save(out_path)
    doc.close()
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成三栏自检样卷")
    ap.add_argument("-o", "--out", default="three_column.pdf")
    args = ap.parse_args()
    print(build(args.out))


if __name__ == "__main__":
    main()
