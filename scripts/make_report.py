# -*- coding: utf-8 -*-
"""校对报告生成器（P0-5 + HTML 可视化）
=====================================================
把校对结果 JSON 生成：
  - 报告.md    （markdown 表格，贴聊天/存档都行）
  - 报告.html  （单文件、图片 base64 内嵌，可直接发给出题老师）

结果 JSON 格式:
{
  "title": "《专题七》校对报告",
  "source": "原稿.pdf",
  "mode": "A（纯题目）",
  "date": "2026-10-16",
  "issues": [
    {"level": "error|doubt|hint",           # error=红(错) doubt=橙(存疑) hint=蓝(提示,不算错)
     "page": 6, "qno": "第一题", "type": "题号错乱",
     "desc": "错在哪里（证据）",
     "correct": "正确答案/修改建议",
     "evidence": "验证依据（自算/程序/原题）",
     "crop": "crops/q_pg06_q07.png"}        # 可选，题目小图
  ],
  "verified": ["第5题：10、8/3、2/9（多值）", ...]   # 可选：已核验清单
}

用法:
  python make_report.py results.json -o 输出目录 [--name 校对报告]
"""
import argparse
import base64
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LEVELS = {
    "error": ("🔴", "错误（必须修改）", "#d32f2f", "#fdecea", "#f2b8b5"),
    "doubt": ("🟠", "存疑（待人工复核）", "#e65100", "#fff4e5", "#ffd8a8"),
    "hint": ("🔵", "提示（不算错误）", "#1565c0", "#e8f1fc", "#bcd7f5"),
    "pass": ("✅", "已核验通过", "#2e7d32", "#e8f5e9", "#c8e6c9"),
}


def img_tag(path, prefix="", max_w=None):
    if path and os.path.exists(path):
        data = base64.b64encode(open(path, "rb").read()).decode()
        style = f' style="max-width:{max_w}px"' if max_w else ""
        return f'<img class="shot" src="data:image/png;base64,{data}"{style}/>'
    return ""


def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def main():
    ap = argparse.ArgumentParser(description="校对报告生成器")
    ap.add_argument("results")
    ap.add_argument("-o", "--out", default="report")
    ap.add_argument("--name", default="校对报告")
    args = ap.parse_args()

    data = json.load(open(args.results, encoding="utf-8-sig"))
    os.makedirs(args.out, exist_ok=True)
    issues = data.get("issues", [])
    counts = {k: sum(1 for it in issues if it.get("level") == k) for k in LEVELS}
    verified = data.get("verified", [])

    # ---------------- markdown ----------------
    md = []
    md.append(f"# {data.get('title', '数学试卷校对报告')}")
    md.append("")
    md.append(f"**来源**：{data.get('source', '-')}　**模式**：{data.get('mode', '-')}　**日期**：{data.get('date', '-')}")
    md.append("")
    md.append(f"**结论**：🔴 错误 {counts['error']} 处 ｜ 🟠 存疑 {counts['doubt']} 处 ｜ 🔵 提示 {counts['hint']} 处（多解类只提示，不计错误）")
    md.append("")
    for key in ("error", "doubt", "hint"):
        group = [it for it in issues if it.get("level") == key]
        if not group:
            continue
        icon, label, *_ = LEVELS[key]
        md.append(f"## {icon} {label}（{len(group)} 处）")
        md.append("")
        md.append("| 页 | 题号 | 类型 | 错在哪（证据） | 正确答案/建议 | 依据 |")
        md.append("|---|---|---|---|---|---|")
        for it in group:
            md.append("| {} | {} | {} | {} | {} | {} |".format(
                it.get("page", ""), md_escape(it.get("qno", "")), md_escape(it.get("type", "")),
                md_escape(it.get("desc", "")), md_escape(it.get("correct", "")),
                md_escape(it.get("evidence", ""))))
        md.append("")
    if verified:
        md.append("## ✅ 已核验通过（答案清单）")
        md.append("")
        for v in verified:
            md.append(f"- {v}")
        md.append("")
    md_path = os.path.join(args.out, f"{args.name}.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(md))

    # ---------------- HTML ----------------
    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    h.append(f"<title>{data.get('title', '校对报告')}</title><style>")
    h.append("""
    body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:920px;margin:0 auto;
         padding:28px 20px 60px;background:#f7f8fa;color:#222;line-height:1.65}
    h1{font-size:24px;margin:0 0 6px} h2{font-size:18px;margin:32px 0 10px;border-left:5px solid #444;padding-left:10px}
    .meta{color:#666;font-size:13.5px;margin-bottom:10px}
    .legend{background:#fff;border:1px dashed #bbb;border-radius:10px;padding:10px 14px;font-size:13px;color:#555;margin:14px 0}
    .card{border:1px solid;border-radius:12px;padding:14px 18px;margin:14px 0;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.05)}
    .badge{display:inline-block;font-size:12.5px;padding:1px 9px;border-radius:20px;color:#fff;margin-right:8px;vertical-align:1px}
    .row{margin:5px 0;font-size:14.5px}
    .label{color:#999;display:inline-block;min-width:4.2em}
    .correct{color:#1b5e20;font-weight:600}
    .desc{font-size:14.5px}
    img.shot{max-width:100%;border:1px solid #ddd;border-radius:8px;margin-top:10px;display:block}
    .verified{background:#fff;border:1px solid #c8e6c9;border-radius:12px;padding:12px 18px}
    .verified li{font-size:14px}
    footer{color:#aaa;font-size:12px;margin-top:36px;text-align:center}
    """)
    h.append("</style></head><body>")
    h.append(f"<h1>{data.get('title', '数学试卷校对报告')}</h1>")
    h.append(f'<div class="meta">来源：{data.get("source", "-")} ｜ 模式：{data.get("mode", "-")} ｜ 日期：{data.get("date", "-")}</div>')
    h.append(f'<div class="legend">🔴 错误＝题目/答案确实写错，必须修改　｜　🟠 存疑＝无法验证且查不到原题，待人工复核　｜　'
             f'🔵 提示＝多解、表述建议等，<b>不算错误</b>（多解题只要答案册写全即为正确）</div>')
    h.append(f'<div class="meta"><b>结论：</b>🔴 错误 {counts["error"]} 处 ｜ 🟠 存疑 {counts["doubt"]} 处 ｜ 🔵 提示 {counts["hint"]} 处 ｜ ✅ 已核验 {len(verified)} 项</div>')

    for key in ("error", "doubt", "hint"):
        group = [it for it in issues if it.get("level") == key]
        if not group:
            continue
        icon, label, fg, bg, bd = LEVELS[key]
        h.append(f"<h2>{icon} {label}（{len(group)} 处）</h2>")
        for it in group:
            h.append(f'<div class="card" style="border-color:{bd};background:{bg}">')
            h.append(f'<div><span class="badge" style="background:{fg}">{label.split("（")[0]}</span>'
                     f'<b>第{it.get("page", "?")}页 · {it.get("qno", "")}</b>　<span style="color:{fg}">{it.get("type", "")}</span></div>')
            h.append(f'<div class="row desc">📍 错在哪：{it.get("desc", "")}</div>')
            if it.get("correct"):
                h.append(f'<div class="row"><span class="label">✅ 正确：</span><span class="correct">{it["correct"]}</span></div>')
            if it.get("evidence"):
                h.append(f'<div class="row"><span class="label">依据：</span>{it["evidence"]}</div>')
            if it.get("crop"):
                h.append(img_tag(it["crop"]))
            h.append("</div>")

    if verified:
        h.append("<h2>✅ 已核验通过（答案清单）</h2>")
        h.append('<div class="verified"><ul>')
        for v in verified:
            h.append(f"<li>{v}</li>")
        h.append("</ul></div>")

    h.append("<footer>由 math-paper-proofreading 技能生成 · 红=错误 / 橙=存疑 / 蓝=提示（多解不算错）</footer>")
    h.append("</body></html>")
    html_path = os.path.join(args.out, f"{args.name}.html")
    open(html_path, "w", encoding="utf-8").write("\n".join(h))

    print(f"报告已生成：\n  {md_path}\n  {html_path}")
    print(f"统计：错误 {counts['error']} / 存疑 {counts['doubt']} / 提示 {counts['hint']} / 已核验 {len(verified)}")


if __name__ == "__main__":
    main()
