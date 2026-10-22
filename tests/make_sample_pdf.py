# -*- coding: utf-8 -*-
"""生成技能自检用的迷你数学试卷 PDF（不依赖任何外部样卷）。

用途:
  python tests/make_sample_pdf.py -o tests/out/_sample/sample_exam.pdf

样卷设计（2 页，8 题，卷末带"参考答案"）:
  - 覆盖选择题/填空/解答三种题型，含图形位置留白；
  - 第 2 页末尾有答案区 → 用于验证 cut_questions 自动拆分；
  - 答案行采用"1．A　2．A　3．B"这种一行多条的常见排法。
"""
import argparse
import os

import pymupdf

PAGES = [
    [
        ("2026 学年七年级数学阶段练习（技能自检样卷）", 15),
        ("一、选择题（每题 3 分，共 9 分）", 11),
        ("1．下列各数中，最小的数是（　　）", 10.5),
        ("A．-3　　B．0　　C．1　　D．2", 10.5),
        ("2．计算 (-2)^3 的结果是（　　）", 10.5),
        ("A．-8　　B．-6　　C．6　　D．8", 10.5),
        ("3．若 a+b=5，ab=6，则 a²+b² 的值为（　　）", 10.5),
        ("A．11　　B．13　　C．15　　D．17", 10.5),
        ("二、填空题（每题 4 分，共 12 分）", 11),
        ("4．单项式 -3x²y 的系数是　　　　．", 10.5),
        ("5．若 |x-2|=3，则 x=　　　　．", 10.5),
        ("6．观察数列 1，4，9，16，…，第 n 项为　　　　．", 10.5),
    ],
    [
        ("三、解答题（每题 6 分，共 12 分）", 11),
        ("7．解方程：2(x-1)=x+3．", 10.5),
        ("8．计算：(-1)^2026 + |−2| − √4．", 10.5),
        ("", 10),
        ("参考答案", 12),
        ("1．A　2．A　3．B", 10.5),
        ("4．-3　5．5　6．n²", 10.5),
        ("7．x=5　8．1", 10.5),
    ],
]


def build(out_path):
    doc = pymupdf.open()
    for lines in PAGES:
        page = doc.new_page(width=595, height=842)
        y = 70
        for text, size in lines:
            if text:
                page.insert_text((60, y), text, fontsize=size, fontname="china-s")
            y += size + 14
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.save(out_path)
    doc.close()
    return out_path


def main():
    ap = argparse.ArgumentParser(description="生成自检样卷 PDF")
    ap.add_argument("-o", "--out", default="sample_exam.pdf")
    args = ap.parse_args()
    print(build(args.out))


if __name__ == "__main__":
    main()
