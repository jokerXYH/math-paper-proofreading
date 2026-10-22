# -*- coding: utf-8 -*-
"""生成双栏测试卷（验证栏检测 / 分栏切题 / 不串栏）。

用法:
  python tests/make_two_column_pdf.py -o tests/out/_sample/two_column.pdf
"""
import argparse
import os

import pymupdf

LEFT = [
    ("1．下列各数中最小的是（　　）", 10.5),
    ("A．-3　　B．0", 10.5),
    ("C．1　　D．2", 10.5),
    ("2．计算 (-2)^3＝（　　）", 10.5),
    ("A．-8　　B．-6", 10.5),
    ("3．若 a+b=5，ab=6，", 10.5),
    ("则 a²+b²＝（　　）", 10.5),
    ("A．11　　B．13", 10.5),
]
RIGHT = [
    ("4．单项式 -3x²y 的系数是（　　）", 10.5),
    ("A．-3　　B．3", 10.5),
    ("5．若 |x-2|=3，则 x＝（　　）", 10.5),
    ("A．5　　B．-1", 10.5),
    ("C．5 或 -1　D．1", 10.5),
    ("6．数列 1，4，9，16，…", 10.5),
    ("第 n 项为（　　）", 10.5),
    ("A．n²　　B．2n", 10.5),
]


def build(out_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 70), "七年级数学双栏练习（技能自检样卷）",
                     fontsize=15, fontname="china-s")
    page.insert_text((60, 105), "一、选择题（每题 3 分）",
                     fontsize=11, fontname="china-s")
    y = 140
    for text, size in LEFT:
        page.insert_text((60, y), text, fontsize=size, fontname="china-s")
        y += 20
    y = 140
    for text, size in RIGHT:
        page.insert_text((320, y), text, fontsize=size, fontname="china-s")
        y += 20
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.save(out_path)
    doc.close()
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成双栏自检样卷")
    ap.add_argument("-o", "--out", default="two_column.pdf")
    args = ap.parse_args()
    print(build(args.out))


if __name__ == "__main__":
    main()
