# -*- coding: utf-8 -*-
"""题目级自动切图（P0-1）
=====================================================
把整页 PDF 按题号自动切成"每题一张小图" + 文本快照，
校验时逐题看图，图形/表格绝不漏看；同时输出题号链诊断。

用法:
  python cut_questions.py 试卷.pdf -o 输出目录 [--dpi 220] [--pages 1,2,5]
输出:
  输出目录/crops/q_pgXX_qYY.png     每题一张小图（跨页题另有 _合并 图）
  输出目录/questions.json           题号/页码/坐标/文本快照/裁剪路径
  输出目录/report.txt               题号链诊断

依赖: pymupdf
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

HEADER_Y = 55      # 页眉线以下才算正文
FOOTER_Y = 792     # 页脚线以上才算正文
LEFT_X_MAX = 130   # 题号必须足够靠左
QN_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]")
OPT_RE = re.compile(r"^\s*[A-DＡ-Ｄ]\s*[.．、]")
SUB_RE = re.compile(r"^\s*[（(]\d{1,2}[）)]")
# 栏目标题/说明类行，不算上一题的跨页延续
SEC_RE = re.compile(r"^\s*([◆⚫⬛◼■●⬤◯⭕▪▫★☆✦✧✱✳]|Part|题型|说明|【)")


def collect_elements(page):
    """返回 (lines, images)，均已剔除页眉页脚与微小图块"""
    lines, images = [], []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if not txt:
                continue
            x0, y0, x1, y1 = ln["bbox"]
            if y1 < HEADER_Y or y0 > FOOTER_Y:
                continue
            lines.append({"text": txt, "bbox": (x0, y0, x1, y1)})
    for im in page.get_image_info():
        x0, y0, x1, y1 = im["bbox"]
        if y1 < HEADER_Y or y0 > FOOTER_Y:
            continue
        if (x1 - x0) < 8 or (y1 - y0) < 8:
            continue
        images.append({"bbox": (x0, y0, x1, y1)})
    return lines, images


def find_anchors(lines):
    """找题号锚点：行首 N. / N．/ N、，排除选项行(A. B.)和小题行(（1）)"""
    anchors = []
    for i, ln in enumerate(lines):
        t = ln["text"]
        if OPT_RE.match(t) or SUB_RE.match(t):
            continue
        m = QN_RE.match(t)
        if not m:
            continue
        x0, y0, x1, y1 = ln["bbox"]
        if x0 > LEFT_X_MAX:
            continue
        rest = t[m.end():].strip()
        if not rest:
            # 允许"纯题号行"，但要求：左边距、下一行紧邻（同一段落的续行）
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if nxt is None or nxt["bbox"][1] - y1 > 32:
                continue
        anchors.append({"qno": int(m.group(1)),
                        "y0": y0, "y1": y1})
    return anchors


def region_of(lines, images, top, bottom):
    """取 [top, bottom) 区间内的元素并集"""
    ls = [l for l in lines if l["bbox"][1] >= top - 2 and l["bbox"][3] <= bottom + 2]
    ims = [g for g in images if g["bbox"][1] >= top - 2 and g["bbox"][3] <= bottom + 2]
    if not ls and not ims:
        return None
    x0 = min([l["bbox"][0] for l in ls] + [g["bbox"][0] for g in ims])
    x1 = max([l["bbox"][2] for l in ls] + [g["bbox"][2] for g in ims])
    y0 = min([l["bbox"][1] for l in ls] + [g["bbox"][1] for g in ims])
    y1 = max([l["bbox"][3] for l in ls] + [g["bbox"][3] for g in ims])
    text = " ".join(l["text"] for l in ls)
    return {"rect": (x0, y0, x1, y1), "lines": ls, "images": ims, "text": text}


def main():
    ap = argparse.ArgumentParser(description="题目级自动切图")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="q_cut")
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--pages", default=None, help="只处理指定页，如 1,2,5")
    ap.add_argument("--merge", action="store_true",
                    help="把跨页题拼成一张合并图（默认仅标记 continues_to）")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    crops_dir = os.path.join(args.out, "crops")
    os.makedirs(crops_dir, exist_ok=True)
    pages_wanted = None
    if args.pages:
        pages_wanted = {int(x) for x in args.pages.split(",") if x.strip()}

    per_page = {}   # pno -> (lines, images, anchors, content_bottom, width, height)
    for i, page in enumerate(doc):
        pno = i + 1
        if pages_wanted and pno not in pages_wanted:
            continue
        lines, images = collect_elements(page)
        anchors = find_anchors(lines)
        cb = max([l["bbox"][3] for l in lines] + [g["bbox"][3] for g in images], default=0)
        per_page[pno] = {
            "lines": lines, "images": images, "anchors": anchors,
            "content_bottom": cb, "w": page.rect.width, "h": page.rect.height,
        }

    questions, warns = [], []
    used_names = set()

    def crop_name(pno, qno, suffix=""):
        base = f"q_pg{pno:02d}_q{qno:02d}{suffix}"
        name = base + ".png"
        k = 2
        while name in used_names:
            name = f"{base}_{k}.png"
            k += 1
        used_names.add(name)
        return name

    for pno in sorted(per_page):
        info = per_page[pno]
        anchors = info["anchors"]
        if not anchors:
            continue
        page = doc[pno - 1]
        for idx, a in enumerate(anchors):
            top = a["y0"] - 6
            if idx + 1 < len(anchors):
                bottom = anchors[idx + 1]["y0"] - 4
            else:
                bottom = info["content_bottom"] + 4
            if bottom - top < 22:
                continue
            reg = region_of(info["lines"], info["images"], top, bottom)
            if reg is None:
                continue
            x0, y0, x1, y1 = reg["rect"]
            cx0 = max(18, x0 - 10)
            cx1 = min(info["w"] - 18, x1 + 12)
            clip = pymupdf.Rect(cx0, max(HEADER_Y, y0 - 4), cx1, min(FOOTER_Y, y1 + 6))
            name = crop_name(pno, a["qno"])
            doc[pno - 1].get_pixmap(dpi=args.dpi, clip=clip).save(
                os.path.join(crops_dir, name))
            questions.append({
                "qno": a["qno"], "page": pno,
                "rect": [round(v, 1) for v in clip],
                "crop": os.path.join(crops_dir, name).replace("\\", "/"),
                "text": reg["text"][:600],
                "continues_to": None,
            })

            # 跨页检测：本题触底且下一页在首个锚点前还有"非栏目标题"的正文内容
            touches_bottom = (bottom >= info["content_bottom"] - 6)
            nxt = per_page.get(pno + 1)
            if touches_bottom and nxt:
                first_anchor_y = nxt["anchors"][0]["y0"] if nxt["anchors"] else FOOTER_Y
                cont_lines = [l for l in nxt["lines"]
                              if l["bbox"][3] <= first_anchor_y - 3 and not SEC_RE.match(l["text"])]
                cont_imgs = [g for g in nxt["images"] if g["bbox"][3] <= first_anchor_y - 3]
                cont_h = max([l["bbox"][3] for l in cont_lines] +
                             [g["bbox"][3] for g in cont_imgs], default=HEADER_Y) - HEADER_Y
                if cont_lines or cont_imgs:
                    if cont_h >= 25:
                        questions[-1]["continues_to"] = pno + 1
                        warns.append(f"⚠ 第{pno}页 题{a['qno']} 可能跨到第{pno+1}页（延续高度 {cont_h:.0f}pt）")
                        if args.merge:
                            y0n = min([l["bbox"][1] for l in cont_lines] +
                                      [g["bbox"][1] for g in cont_imgs])
                            y1n = max([l["bbox"][3] for l in cont_lines] +
                                      [g["bbox"][3] for g in cont_imgs])
                            xn0 = min([l["bbox"][0] for l in cont_lines] +
                                      [g["bbox"][0] for g in cont_imgs])
                            xn1 = max([l["bbox"][2] for l in cont_lines] +
                                      [g["bbox"][2] for g in cont_imgs])
                            clip2 = pymupdf.Rect(max(18, xn0 - 10), max(HEADER_Y, y0n - 4),
                                                 min(nxt["w"] - 18, xn1 + 12), min(FOOTER_Y, y1n + 6))
                            allw = max(clip.width, clip2.width)
                            h1 = clip.height
                            new = pymupdf.open()
                            pg = new.new_page(width=allw, height=h1 + clip2.height + 8)
                            pg.show_pdf_page(pymupdf.Rect(0, 0, clip.width, clip.height),
                                             doc, pno - 1, clip=clip)
                            pg.show_pdf_page(pymupdf.Rect(0, clip.height + 8,
                                                          clip2.width, h1 + clip2.height + 8),
                                             doc, pno, clip=clip2)
                            mname = crop_name(pno, a["qno"], "_合并")
                            pg.get_pixmap(dpi=args.dpi).save(os.path.join(crops_dir, mname))
                            questions[-1]["crop_merged"] = os.path.join(crops_dir, mname).replace("\\", "/")
                            new.close()

    # 题号链诊断
    qnos = [q["qno"] for q in questions]
    diag = []
    for a, b in zip(qnos, qnos[1:]):
        if b == a:
            diag.append(f"题号重复: {a}")
        elif b < a and b != 1:
            diag.append(f"题号回退: {a} -> {b}（检查是否编号错乱或按题型重新编号）")

    with open(os.path.join(args.out, "questions.json"), "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(f"文件: {args.pdf}\n")
        f.write(f"切出题目: {len(questions)} 张\n")
        f.write("题号诊断:\n")
        f.write("\n".join("  - " + d for d in diag) if diag else "  （无异常）")
        f.write("\n")
        if warns:
            f.write("\n".join(warns) + "\n")

    print(f"切出题目: {len(questions)} 张 → {os.path.join(args.out, 'crops')}")
    if diag:
        print("题号诊断:", *diag, sep="\n  - ")
    for w in warns:
        print(w)
    print(f"清单: {os.path.join(args.out, 'questions.json')}")


if __name__ == "__main__":
    main()
