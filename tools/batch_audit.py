# -*- coding: utf-8 -*-
"""批量体检：一次跑多份 PDF，快速发现版式/识别问题（校准用）。

用法:
  python tools/batch_audit.py 试卷样本/ -o 体检报告
  python tools/batch_audit.py 试卷样本/ -o 体检报告 --cut      # 同时切题（慢，产出小图）
  python tools/batch_audit.py a.pdf b.pdf -o 体检报告

输出:
  体检报告/audit.json   机器可读
  体检报告/audit.md     人读表格（按"疑似问题"排序）

关注指标:
  - 文本层覆盖率：扫描件会很低
  - 多栏页数：1–4 栏
  - 题号数 / 重复率 / 0 号误判
  - 题号回退（跨章节重新编号是正常的，需要人看）
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import pymupdf  # noqa: E402
import recognition as rec  # noqa: E402


def audit_one(path, cut=False, out_dir=None):
    name = os.path.splitext(os.path.basename(path))[0]
    doc = pymupdf.open(path)
    layouts = rec.analyze_document(doc)
    pages = len(doc)
    text_pages = sum(1 for p in doc if len(p.get_text().strip()) > 40)
    col_pages, anchor_total, warns = [], 0, []
    qnos = []
    no_anchor_pages = []
    for i, lay in enumerate(layouts):
        if lay is None:
            continue
        if lay["columns"]:
            col_pages.append((i + 1, len(lay["columns"])))
        if not lay["anchors"]:
            no_anchor_pages.append(i + 1)
        anchor_total += len(lay["anchors"])
        qnos.extend(a["qno"] for a in lay["anchors"])
        for w in lay["warnings"]:
            warns.append(f"p{i+1}:{w}")
    dup = len(qnos) - len(set(qnos))
    zeros = sum(1 for q in qnos if q == 0)
    back = sum(1 for a, b in zip(qnos, qnos[1:]) if b < a and b != 1)
    ratio = text_pages / pages if pages else 0
    item = {
        "file": path, "name": name, "pages": pages, "text_pages": text_pages,
        "text_ratio": round(ratio, 2),
        "col_pages": len(col_pages), "col_detail": col_pages[:20],
        "anchors": anchor_total, "no_anchor_pages": no_anchor_pages[:20],
        "unique_qno": len(set(qnos)), "dup_qno": dup, "zero_qno": zeros,
        "back_steps": back, "warnings": warns[:20],
    }
    flags = []
    if ratio < 0.5:
        flags.append("疑似扫描件/OCR后需复核")
    if pages and len(no_anchor_pages) > pages * 0.5:
        flags.append("过半页面无题号")
    if zeros:
        flags.append(f"{zeros} 个 0 号误判")
    if anchor_total and dup / max(1, len(qnos)) > 0.35:
        flags.append("题号重复率高（可能跨章节重新编号）")
    if col_pages and any(n not in (2, 3) for _, n in col_pages):
        flags.append("存在 4 栏或异常栏数")
    item["flags"] = flags

    if cut and out_dir:
        cut_dir = os.path.join(out_dir, name)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "cut_questions.py"),
                            path, "-o", cut_dir, "--dpi", "100"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        qs_p = os.path.join(cut_dir, "questions.json")
        ans_p = os.path.join(cut_dir, "answers.json")
        item["cut_ok"] = r.returncode == 0
        item["cut_questions"] = len(json.load(open(qs_p, encoding="utf-8"))) \
            if os.path.exists(qs_p) else 0
        item["cut_answers"] = len(json.load(open(ans_p, encoding="utf-8"))) \
            if os.path.exists(ans_p) else 0
        item["cut_output"] = cut_dir
    doc.close()
    return item


def main():
    ap = argparse.ArgumentParser(description="批量体检 PDF")
    ap.add_argument("inputs", nargs="+", help="文件或目录")
    ap.add_argument("-o", "--out", default="audit_out")
    ap.add_argument("--cut", action="store_true", help="同时跑切题（慢）")
    args = ap.parse_args()

    paths = []
    for x in args.inputs:
        if os.path.isdir(x):
            paths.extend(sorted(glob.glob(os.path.join(x, "*.pdf"))))
        else:
            paths.append(x)
    paths = [p for p in paths if p.lower().endswith(".pdf") and os.path.exists(p)]
    if not paths:
        sys.exit("没有可处理的 PDF")

    os.makedirs(args.out, exist_ok=True)
    items = []
    for i, p in enumerate(paths, 1):
        print(f"[{i}/{len(paths)}] {os.path.basename(p)}")
        try:
            items.append(audit_one(p, args.cut, args.out))
        except Exception as e:
            items.append({"file": p, "name": os.path.basename(p),
                          "error": str(e)[:200], "flags": ["解析失败"]})

    items.sort(key=lambda x: (len(x.get("flags", [])), -x.get("pages", 0)), reverse=True)
    json.dump({"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "items": items},
              open(os.path.join(args.out, "audit.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    md = ["# 批量体检报告", "", f"生成: {datetime.now():%Y-%m-%d %H:%M}", "",
          "| 文件 | 页 | 文本页 | 多栏页 | 题号 | 唯一 | 0号 | 回退 | 结论 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for x in items:
        if x.get("error"):
            md.append(f"| {x['name']} | - | - | - | - | - | - | - | ❌ {x['error']} |")
            continue
        flag = "；".join(x["flags"]) or "✅ 正常"
        md.append(f"| {x['name']} | {x['pages']} | {x['text_pages']} | "
                  f"{x['col_pages']} | {x['anchors']} | {x['unique_qno']} | "
                  f"{x['zero_qno']} | {x['back_steps']} | {flag} |")
    open(os.path.join(args.out, "audit.md"), "w", encoding="utf-8").write(
        "\n".join(md) + "\n")
    print(f"\n体检报告: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
