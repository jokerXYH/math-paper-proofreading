# -*- coding: utf-8 -*-
"""错别字/漏字自动筛查（P1-8）
=====================================================
规则引擎做"高召回候选"扫描（错字表 + 叠字 + 标点 + 括号配对 + 数列加号等），
同时生成一份喂给大模型的通读提示词（语义类漏字/病句交给 LLM 第二阶段）。

用法:
  python typo_scan.py 试卷.pdf -o out [--extra-dict 我的错字表.txt]
输出:
  out/typo_candidates.json   候选清单（含页码/坐标/整行/建议）
  out/report.txt             人读汇总
  out/llm_review_prompt.md   LLM 通读提示词（把全文带上，交给模型找语义类问题）

⚠ 纪律: 本工具输出的是"候选"，必须逐条回渲染图复核后才可进正式报告！
额外错字表格式（每行）: 错误词→正确词   或   ^正则$→正确词
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

HEADER_Y, FOOTER_Y = 55, 792

# —— 种子错字表（数学试卷常见）——
SEED = [
    (r"变化而变(?!化)", "变化而变化", "疑似漏“化”字", "高"),
    (r"例竖式", "列竖式", "错别字", "高"),
    (r"己知", "已知", "错别字", "高"),
    (r"圆椎", "圆锥", "错别字", "高"),
    (r"直经", "直径", "错别字", "高"),
    (r"半经", "半径", "错别字", "高"),
    (r"对称抽", "对称轴", "错别字", "高"),
    (r"全等形?型", "全等型/全等图形", "疑似错别字", "中"),
    (r"的的|了了|是是|和和|在在|与与|数数(?=[字学])", "", "疑似多字/叠字", "中"),
]
WHITELIST_DUP = set("渐慢常刚往仅缓悄默深浅高大一步层处次个件天年月日点滴丝些微略面方个团满数")
PUNCT_DUP = re.compile(r"([，。；：！？]{2,})")
FULLWIDTH_DIGIT = re.compile(r"[０-９]")
SERIES_PLUS = re.compile(r"[A-Za-z]\d(?:\s*[+＋]\s*(?:[A-Za-z]\d|…|\.{2,})){2,}")
ASCII_IN_CJK = re.compile(r"[\u4e00-\u9fff]\s*[,;:]\s*[\u4e00-\u9fff]")
BRACKETS = [("（", "）"), ("《", "》"), ("【", "】"), ("“", "”")]


def scan_text(text, page_no, rules):
    out = []
    for y, line in text:
        for pat, fix, note, sev in rules:
            for m in re.finditer(pat, line):
                out.append({"page": page_no, "y": round(y, 1), "rule": "错字表",
                            "match": m.group(0), "fix": fix, "note": note,
                            "sev": sev, "line": line[:90]})
        for m in re.finditer(r"([\u4e00-\u9fff])\1", line):
            if m.group(1) in WHITELIST_DUP:
                continue
            out.append({"page": page_no, "y": round(y, 1), "rule": "叠字",
                        "match": m.group(0), "fix": "", "note": "疑似重复字",
                        "sev": "中", "line": line[:90]})
        for m in PUNCT_DUP.finditer(line):
            out.append({"page": page_no, "y": round(y, 1), "rule": "标点重复",
                        "match": m.group(0), "fix": m.group(1), "note": "重复标点",
                        "sev": "低", "line": line[:90]})
        for m in FULLWIDTH_DIGIT.finditer(line):
            out.append({"page": page_no, "y": round(y, 1), "rule": "全角数字",
                        "match": m.group(0), "fix": "半角数字", "note": "全角数字",
                        "sev": "低", "line": line[:90]})
        for m in SERIES_PLUS.finditer(line):
            out.append({"page": page_no, "y": round(y, 1), "rule": "数列疑似加号",
                        "match": m.group(0), "fix": "数列之间应为逗号",
                        "note": "疑似把逗号写成加号；但若是求和式请忽略", "sev": "低",
                        "line": line[:90]})
        for m in ASCII_IN_CJK.finditer(line):
            out.append({"page": page_no, "y": round(y, 1), "rule": "中英标点混用",
                        "match": m.group(0), "fix": "改用全角标点", "note": "正文中的半角标点",
                        "sev": "低", "line": line[:90]})
    return out


def main():
    ap = argparse.ArgumentParser(description="错别字/漏字自动筛查")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="typo_out")
    ap.add_argument("--extra-dict", default=None, help="额外错字表（错误→正确 每行一条）")
    args = ap.parse_args()

    rules = list(SEED)
    if args.extra_dict and os.path.exists(args.extra_dict):
        for ln in open(args.extra_dict, encoding="utf-8-sig").read().splitlines():
            ln = ln.strip()
            if not ln or "→" not in ln:
                continue
            wrong, right = [x.strip() for x in ln.split("→", 1)]
            rules.append((wrong, right, "自定义错字表", "高"))

    doc = pymupdf.open(args.pdf)
    os.makedirs(args.out, exist_ok=True)
    candidates, full_text, page_issues = [], [], []
    for i, page in enumerate(doc):
        pno = i + 1
        lines = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                t = "".join(s["text"] for s in ln["spans"]).strip()
                x0, y0, x1, y1 = ln["bbox"]
                if not t or y1 < HEADER_Y or y0 > FOOTER_Y:
                    continue
                lines.append((y0, t))
        lines.sort()
        candidates.extend(scan_text(lines, pno, rules))
        # 页级括号/引号配对
        raw = "\n".join(t for _, t in lines)
        for a, b in BRACKETS:
            if raw.count(a) != raw.count(b):
                page_issues.append({"page": pno, "rule": "括号不配对",
                                    "match": f"{a}×{raw.count(a)} / {b}×{raw.count(b)}",
                                    "fix": "", "note": "本页括号/引号数量不配对",
                                    "sev": "中", "line": ""})
        full_text.append(f"===== 第{pno}页 =====\n" + raw)

    all_c = candidates + page_issues
    json.dump(all_c, open(os.path.join(args.out, "typo_candidates.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    sev_order = {"高": 0, "中": 1, "低": 2}
    all_c.sort(key=lambda c: (sev_order.get(c["sev"], 3), c["page"]))
    rep = [f"候选总数: {len(all_c)}（高 {sum(1 for c in all_c if c['sev']=='高')} / "
           f"中 {sum(1 for c in all_c if c['sev']=='中')} / 低 {sum(1 for c in all_c if c['sev']=='低')}）", ""]
    for c in all_c:
        rep.append(f"[{c['sev']}][{c['rule']}] 第{c['page']}页 “{c['match']}”"
                   + (f" → {c['fix']}" if c['fix'] else "")
                   + f"（{c['note']}）")
    rep.append("")
    rep.append("⚠ 以上均为候选，必须逐条回渲染图复核后才能进正式报告。")
    open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8").write("\n".join(rep))

    # LLM 通读提示词（第二阶段的语义检查）
    prompt = [
        "# 错别字/漏字通读任务（LLM 第二阶段）",
        "",
        "你是资深数学教研编辑。下面是某初中数学试卷的全文（分页，页眉页脚已剔除）。",
        "请找出：**错别字、漏字、多字、标点误用（含数列逗号误写成加号）**。",
        "注意：",
        "1. 数学表达式、变量名、公式本身不算问题；",
        "2. 只报「确定有问题」和「高度怀疑」的，不确定的也列出但标注 不确定；",
        "3. 输出 JSON 列表，保存为 `typo_review.json`，格式：",
        "   [{\"page\": 3, \"line\": \"原句片段\", \"issue\": \"问题描述\", \"fix\": \"修改建议\", \"confidence\": \"高|中|不确定\"}]",
        "",
        "--- 试卷全文 ---",
        "",
        "\n\n".join(full_text),
    ]
    open(os.path.join(args.out, "llm_review_prompt.md"), "w", encoding="utf-8").write("\n".join(prompt))

    print("\n".join(rep[:16]))
    if len(rep) > 17:
        print(f"… 完整清单见 {os.path.join(args.out, 'report.txt')}")
    print(f"\n候选JSON: {os.path.join(args.out, 'typo_candidates.json')}")
    print(f"LLM通读提示词: {os.path.join(args.out, 'llm_review_prompt.md')}")


if __name__ == "__main__":
    main()
