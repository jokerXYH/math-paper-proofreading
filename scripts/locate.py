# -*- coding: utf-8 -*-
"""批注定位助手（P0-2）
=====================================================
输入关键词，自动在 PDF 里找坐标，生成可直接粘贴进批注 spec 的
JSON 片段——告别手填坐标。

用法:
  python locate.py 试卷.pdf "变化而变"                       # 全卷搜索
  python locate.py 试卷.pdf "正数" --page 1                  # 指定页
  python locate.py 试卷.pdf "b-1" "b−1" --page 8 --expand 4  # 多关键词、外扩4pt
输出:
  命中清单（页码/坐标/上下文行） + spec 片段（--json 只输出 JSON）

说明: 用于 draw_annotations.py 的 "marks"；把 color 改成 red/orange/blue 即可。
"""
import argparse
import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf


def context_of(page, rect):
    """找与 rect 相交的文本行，输出上下文"""
    best = None
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            bb = pymupdf.Rect(ln["bbox"])
            if bb.intersects(rect):
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if txt and (best is None or len(txt) > len(best)):
                    best = txt
    return (best or "")[:80]


def main():
    ap = argparse.ArgumentParser(description="批注定位助手")
    ap.add_argument("pdf")
    ap.add_argument("keywords", nargs="+", help="关键词（可多个，或的关系）")
    ap.add_argument("--page", type=int, default=None, help="只搜指定页（1 起）")
    ap.add_argument("--expand", type=float, default=2.0, help="坐标外扩 pt（默认2）")
    ap.add_argument("--color", default="red", help="建议颜色 red/orange/blue")
    ap.add_argument("--json", action="store_true", help="只输出 JSON 片段")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    pages = [args.page - 1] if args.page else range(len(doc))
    hits = []
    for pno in pages:
        page = doc[pno]
        for kw in args.keywords:
            for r in page.search_for(kw):
                rect = pymupdf.Rect(r.x0 - args.expand, r.y0 - args.expand,
                                    r.x1 + args.expand, r.y1 + args.expand)
                hits.append({"page": pno + 1, "kw": kw, "rect": rect,
                             "ctx": context_of(page, r)})
    # 去重（同一位置多关键词命中）
    uniq, seen = [], set()
    for h in hits:
        key = (h["page"], round(h["rect"].x0), round(h["rect"].y0))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)

    spec_lines = []
    for h in uniq:
        r = h["rect"]
        spec_lines.append(
            '    {{"page": {p}, "rect": [{x0}, {y0}, {x1}, {y1}], "color": "{c}", "width": 1.6}}'.format(
                p=h["page"], x0=round(r.x0, 1), y0=round(r.y0, 1),
                x1=round(r.x1, 1), y1=round(r.y1, 1), c=args.color))

    if args.json:
        print('{\n  "marks": [')
        print(",\n".join(spec_lines))
        print("  ]\n}")
        return

    if not uniq:
        print("未命中任何关键词。可尝试：关键词截短、去标点、换全角/半角。")
        return
    print(f"命中 {len(uniq)} 处：")
    for h in uniq:
        r = h["rect"]
        print(f"  [p{h['page']}] “{h['kw']}”  rect=[{r.x0:.1f}, {r.y0:.1f}, {r.x1:.1f}, {r.y1:.1f}]")
        print(f"        上下文: {h['ctx']}")
    print("\n可直接粘贴进 spec 的片段（颜色按需改 red/orange/blue）:")
    print('"marks": [')
    print(",\n".join(spec_lines))
    print("]")


if __name__ == "__main__":
    main()
