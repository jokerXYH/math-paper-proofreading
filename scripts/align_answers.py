# -*- coding: utf-8 -*-
"""题目与答案分离时的自动对齐（P1-6）
=====================================================
场景：题目PDF 和 答案文件（PDF/TXT）是分开的两个文件（教辅常态）。
按题号自动把两者配对，输出：配对结果 + 缺答案清单 + 多余答案清单。

用法:
  python align_answers.py 题目.pdf 答案.pdf -o out
  python align_answers.py 题目.pdf 答案.txt -o out
输出:
  out/alignment.json   配对结果（供后续答案核对/报告使用）
  out/report.txt       人读汇总

对齐算法（双指针、顺序敏感，容忍题号重复/跳号）:
  答案号与当前题目号不一致时，向前推进题目指针直到同号；找不到同号 → 多余答案；
  被跳过的题目 → 缺答案。题号重复时按出现顺序依次配对。
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cut_questions as cq  # noqa: E402  复用题号锚点/答案区逻辑
import recognition as rec  # noqa: E402

# 答案编号：数字 + .．、:：，且后面不是数字（排除小数 3.5、数字列表 1、2、3）
MARK_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[.．、:：]\s*(?!\d)")


def questions_of(pdf_path):
    """题目 PDF → 按阅读顺序的题号列表 [{qno, page}]（栏感知）"""
    doc = pymupdf.open(pdf_path)
    out = []
    layouts = rec.analyze_document(doc)
    for i, page in enumerate(doc):
        lay = layouts[i]
        anchors = lay["anchors"]
        ai = cq.find_answer_start(lay["ordered"])   # 卷末答案区不算题目
        if ai is not None:
            cut_y = lay["ordered"][ai]["y0"]
            anchors = [a for a in anchors if a["y0"] < cut_y - 2]
            out.extend({"qno": a["qno"], "page": i + 1, "column": a["col"]}
                       for a in anchors)
            break
        out.extend({"qno": a["qno"], "page": i + 1, "column": a["col"]}
                   for a in anchors)
    return out


def answers_of(path):
    """答案文件（pdf 或 txt）→ [{qno, text, page}]，支持行首块式与行内连续式"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".pdf", ".txt", ".md"):
        sys.exit(f"不支持的答案文件类型: {ext}（请用 PDF / TXT / MD）")
    lines = []
    if path.lower().endswith(".pdf"):
        doc = pymupdf.open(path)
        for i, page in enumerate(doc):
            for ln in page.get_text().splitlines():
                lines.append((i + 1, ln))
    else:
        with open(path, encoding="utf-8-sig") as f:
            for ln in f.read().splitlines():
                lines.append((1, ln))

    pairs = []
    cur = None
    for pno, raw in lines:
        line = raw.strip()
        if not line:
            continue
        ms = list(MARK_RE.finditer(line))
        if ms:
            if cur:
                pairs.append(cur)
                cur = None
            for k, m in enumerate(ms):
                start = m.end()
                end = ms[k + 1].start() if k + 1 < len(ms) else len(line)
                seg = line[start:end].strip(" \t．.、:：;；")
                if seg:
                    if k == len(ms) - 1:
                        cur = {"qno": int(m.group(1)), "text": seg, "page": pno}
                    else:
                        pairs.append({"qno": int(m.group(1)), "text": seg, "page": pno})
                else:
                    cur = {"qno": int(m.group(1)), "text": "", "page": pno}
        elif cur is not None:
            cur["text"] = (cur["text"] + " " + line).strip()
    if cur:
        pairs.append(cur)
    pairs = [p for p in pairs if p["text"]]
    return pairs


def main():
    ap = argparse.ArgumentParser(description="题目/答案分离对齐")
    ap.add_argument("questions_pdf")
    ap.add_argument("answers_file", help="答案 PDF 或 TXT")
    ap.add_argument("-o", "--out", default="align_out")
    args = ap.parse_args()

    qs = questions_of(args.questions_pdf)
    ans = answers_of(args.answers_file)
    os.makedirs(args.out, exist_ok=True)

    pairs, missing_q, extra_a = [], [], []
    qi = 0
    for a in ans:
        found = None
        j = qi
        while j < len(qs):
            if qs[j]["qno"] == a["qno"]:
                found = j
                break
            j += 1
        if found is None:
            extra_a.append(a)
        else:
            for k in range(qi, found):
                missing_q.append(qs[k])
            pairs.append({"qno": a["qno"],
                          "question_page": qs[found]["page"],
                          "answer": a["text"], "answer_page": a["page"]})
            qi = found + 1
    for k in range(qi, len(qs)):
        missing_q.append(qs[k])

    result = {"pairs": pairs, "missing_answers": missing_q, "extra_answers": extra_a}
    with open(os.path.join(args.out, "alignment.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    rep = [f"题目数: {len(qs)}　答案条目: {len(ans)}　已配对: {len(pairs)}",
           f"缺答案题目: {len(missing_q)}　多余答案: {len(extra_a)}", ""]
    if missing_q:
        rep.append("缺答案（题目有、答案无）:")
        for m in missing_q:
            rep.append(f"  第{m['page']}页 题{m['qno']}")
    if extra_a:
        rep.append("多余答案（答案有、题目无）:")
        for e in extra_a:
            rep.append(f"  [答案第{e['page']}页] {e['qno']}. {e['text'][:40]}")
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rep))
    print("\n".join(rep))
    print(f"\n配对明细: {os.path.join(args.out, 'alignment.json')}")


if __name__ == "__main__":
    main()
