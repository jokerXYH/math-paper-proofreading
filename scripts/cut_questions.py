# -*- coding: utf-8 -*-
"""题目级自动切图（栏感知 · 答案区拆分）
=====================================================
把整页 PDF 按题号自动切成"每题一张小图" + 文本快照，
校验时逐题看图，图形/表格绝不漏看；同时输出题号链诊断。

相比按 y 排序的朴素切法，本版：
  - 双栏版面按栏切割，左右栏不会串题、串图；
  - 题号锚定结合左边距/字号/行首，减少选项与小题目录误判；
  - 卷末"参考答案/解析"自动拆到 answers.json。

用法:
  python cut_questions.py 试卷.pdf -o 输出目录 [--dpi 220] [--pages 1,2,5]
  python cut_questions.py 试卷.pdf -o 输出目录 --keep-answers   # 不拆分答案区
  python cut_questions.py 试卷.pdf -o 输出目录 --no-columns     # 强制单栏
输出:
  输出目录/crops/q_pgXX_qYY.png     每题一张小图（跨页/跨栏另有 合并 图）
  输出目录/crops/a_pgXX_qYY.png     答案区每条答案的小图
  输出目录/questions.json           题号/页码/栏/坐标/文本快照/裁剪路径
  输出目录/answers.json             答案区清单
  输出目录/report.txt               题号链 + 版面诊断 + 答案区信息

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

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import recognition as rec  # noqa: E402

HEADER_Y = 55      # 页眉线以下才算正文
FOOTER_Y = 792     # 页脚线以上才算正文
LEFT_X_MAX = 130   # 单栏兜底：题号必须足够靠左
QN_RE = rec.QN_RE
OPT_RE = rec.OPT_RE
SUB_RE = rec.SUB_RE
SEC_RE = rec.SEC_RE
# 答案区标题（独占一行、短）：参考答案 / 答案与解析 / 试题解析 / 解析
ANSWER_HEAD_RE = re.compile(
    r"^(?:参考)?答案(?:\s*与?\s*(?:解析|详解|试题解析))?$"
    r"|^解析$|^详解$"
)
# 答案区内部编号（允许后接数字，靠"题号递增"过滤小数）
ANS_MARK_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[.．、]\s*")
# 章节/栏目标题：用于判断题号是否属于"知识清单"等非题目条目
SEC_LABEL_RE = re.compile(
    r"知识清单|知识点|考点梳理|知识梳理|方法总结|课堂例题|例题|练习|习题|作业|检测|复习|专题|第[一二三四五六七八九十\d]+讲|Part")
# 题干特征词：有这些词基本可以确认是题目
QUESTION_HINT_RE = re.compile(
    r"[？?]|（\s*）|\(\s*\)|求|计算|解|若|已知|如图|下列|则|证明|画出|填空|选择|判断|化简")
# 定义/概念句式：开头知识清单里常见，短句且无题干特征时判为非题目
DEFINITION_RE = re.compile(r"叫做|叫作|称为|概念|定义|分为[两三四]类")


# ---------------- 兼容旧接口（align_answers 等仍在用） ----------------
def collect_elements(page):
    """返回 (lines, images)，均已剔除页眉页脚与微小图块。"""
    lay = rec.analyze_page(page, HEADER_Y, FOOTER_Y)
    lines = [{"text": l["text"], "bbox": l["bbox"]} for l in lay["ordered"]]
    images = [{"bbox": g["bbox"]} for g in lay["images"]]
    return lines, images


def find_anchors(lines):
    """旧版单栏锚点（无栏信息时兜底）。"""
    anchors = []
    for i, ln in enumerate(lines):
        t = ln["text"]
        if OPT_RE.match(t) or SUB_RE.match(t):
            continue
        m = QN_RE.match(t)
        if not m:
            continue
        if int(m.group(1)) < 1 or t[m.end():m.end() + 1].isdigit():
            continue
        x0, y0, x1, y1 = ln["bbox"]
        if x0 > LEFT_X_MAX:
            continue
        rest = t[m.end():].strip()
        if not rest:
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if nxt is None or nxt["bbox"][1] - y1 > 32:
                continue
        anchors.append({"qno": int(m.group(1)), "y0": y0, "y1": y1})
    return anchors


def find_answer_start(lines):
    """找答案区标题行（参考答案/答案与解析/解析…），返回下标或 None。"""
    for i, ln in enumerate(lines):
        t = re.sub(r"\s+", "", ln["text"])
        if not t or len(t) > 16:
            continue
        if ANSWER_HEAD_RE.match(t):
            return i
    return None


def merge_clips(doc, p1, clip1, p2, clip2, out_path, dpi):
    """把两段裁剪（可跨页/跨栏）纵向拼成一张图。"""
    allw = max(clip1.width, clip2.width)
    new = pymupdf.open()
    pg = new.new_page(width=allw, height=clip1.height + clip2.height + 8)
    pg.show_pdf_page(pymupdf.Rect(0, 0, clip1.width, clip1.height),
                     doc, p1, clip=clip1)
    pg.show_pdf_page(pymupdf.Rect(0, clip1.height + 8, clip2.width,
                                  clip1.height + 8 + clip2.height),
                     doc, p2, clip=clip2)
    pg.get_pixmap(dpi=dpi).save(out_path)
    new.close()


def lines_text(ls):
    """按视觉行重组文本：同一水平带的碎片按 x 排序，避免上标/公式碎片跑到句首。"""
    rows = []
    for l in sorted(ls, key=lambda x: (x["y0"], x["x0"])):
        if rows and l["y0"] < rows[-1]["y1"] - 2:
            rows[-1]["items"].append(l)
            rows[-1]["y1"] = max(rows[-1]["y1"], l["y1"])
        else:
            rows.append({"y0": l["y0"], "y1": l["y1"], "items": [l]})
    out = []
    for row in rows:
        out.append(" ".join(x["text"] for x in sorted(row["items"], key=lambda x: x["x0"])))
    return " ".join(out)


def region_of(lines, images, top, bottom, col_bounds, col):
    """取 [top,bottom) ∩ 本栏 的元素并集（杜绝串栏）。"""
    cx0, cx1 = col_bounds

    def in_col(l):
        if col is None:
            return True          # 通栏题：整页宽度都属于本题
        if l["col"] is None:
            # 通栏/跨栏行不属于任何单栏题目，排除（否则会把邻栏文字拼进本题）
            return l["x0"] >= cx0 - 4 and l["x1"] <= cx1 + 4
        return l["col"] == col

    ls = [l for l in lines if l["y0"] >= top - 2 and l["y1"] <= bottom + 2 and in_col(l)]
    ims = [g for g in images if g["y0"] >= top - 2 and g["y1"] <= bottom + 2 and in_col(g)]
    if not ls and not ims:
        return None
    x0 = min([l["x0"] for l in ls] + [g["x0"] for g in ims])
    x1 = max([l["x1"] for l in ls] + [g["x1"] for g in ims])
    y0 = min([l["y0"] for l in ls] + [g["y0"] for g in ims])
    y1 = max([l["y1"] for l in ls] + [g["y1"] for g in ims])
    text = lines_text(ls)
    return {"rect": (x0, y0, x1, y1), "lines": ls, "images": ims, "text": text}


def main():
    ap = argparse.ArgumentParser(description="题目级自动切图（栏感知）")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="q_cut")
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--pages", default=None, help="只处理指定页，如 1,2,5")
    ap.add_argument("--merge", action="store_true",
                    help="把跨页/跨栏题拼成一张合并图")
    ap.add_argument("--keep-answers", action="store_true",
                    help="不拆分答案区：卷末参考答案仍按题号切成题目（兼容旧行为）")
    ap.add_argument("--no-columns", action="store_true",
                    help="强制按单栏处理（栏检测误判时用）")
    args = ap.parse_args()

    doc = pymupdf.open(args.pdf)
    if not any(p.get_text().strip() for p in doc):
        print("⚠ 未检测到文本层（扫描版/图片 PDF）：无法按题号自动切分。\n"
              "  请先运行 ocr_pdf.py 或按 references/toolchain.md 做 OCR，再重跑。")
    crops_dir = os.path.join(args.out, "crops")
    os.makedirs(crops_dir, exist_ok=True)
    pages_wanted = None
    if args.pages:
        pages_wanted = {int(x) for x in args.pages.split(",") if x.strip()}

    per_page = {}
    layouts = rec.analyze_document(doc, pages=pages_wanted)
    for i, page in enumerate(doc):
        pno = i + 1
        if pages_wanted and pno not in pages_wanted:
            continue
        lay = layouts[i]
        if args.no_columns:
            lay["columns"] = []
            for l in lay["lines"]:
                l["col"] = 0
            lay["anchors"] = rec.question_anchors(lay["ordered"], [])
        lay["content_bottom"] = max(
            [l["y1"] for l in lay["lines"]] + [g["y1"] for g in lay["images"]],
            default=0)
        lay["content_left"] = min([l["x0"] for l in lay["lines"]], default=18)
        lay["content_right"] = max([l["x1"] for l in lay["lines"]], default=page.rect.width - 18)
        ai = None if args.keep_answers else find_answer_start(lay["ordered"])
        lay["answer_y"] = lay["ordered"][ai]["y0"] if ai is not None else None
        per_page[pno] = lay

    questions, answers, warns = [], [], []
    used_names = set()
    layout_warns = []
    cur_section = None

    def crop_name(pno, qno, suffix="", prefix="q"):
        base = f"{prefix}_pg{pno:02d}_q{qno:02d}{suffix}"
        name = base + ".png"
        k = 2
        while name in used_names:
            name = f"{base}_{k}.png"
            k += 1
        used_names.add(name)
        return name

    answer_from = None
    for pno in sorted(per_page):
        if per_page[pno]["answer_y"] is not None:
            answer_from = (pno, per_page[pno]["answer_y"])
            break

    for pno in sorted(per_page):
        lay = per_page[pno]
        if lay["warnings"]:
            layout_warns.extend(f"第{pno}页: {w}" for w in lay["warnings"])
        anchors = lay["anchors"]
        # 记录每个题号所在的章节标题（按阅读顺序推进）
        sec_by_idx = {}
        for idx, ln in enumerate(lay["ordered"]):
            t = ln["text"].strip()
            if len(t) <= 20 and SEC_LABEL_RE.search(t):
                cur_section = t[:24]
            sec_by_idx[idx] = cur_section
        if answer_from and pno > answer_from[0]:
            continue
        if answer_from and pno == answer_from[0]:
            anchors = [a for a in anchors if a["y0"] < answer_from[1] - 2]
        if not anchors:
            continue

        for idx, a in enumerate(anchors):
            col = a["col"]
            top = a["y0"] - 6
            next_any = anchors[idx + 1] if idx + 1 < len(anchors) else None
            bottom_any = next_any["y0"] - 4 if next_any else lay["content_bottom"] + 4
            if answer_from and pno == answer_from[0]:
                bottom_any = min(bottom_any, answer_from[1] - 4)

            # 通栏题干 + 多栏解答：本栏内出现"明显跨栏"的通栏行 → 整题按通栏处理
            same_col = []
            if col is not None:
                same_col = [x for x in anchors[idx + 1:] if x["col"] == col]
                col_bottom = same_col[0]["y0"] - 4 if same_col \
                    else rec.column_bottom(lay["lines"], col) + 4
                if answer_from and pno == answer_from[0]:
                    col_bottom = min(col_bottom, answer_from[1] - 4)
                cb0 = rec.column_bounds(lay["columns"], col, lay["w"], 10)
                cw = max(1.0, cb0[1] - cb0[0])
                probe = [l for l in lay["lines"]
                         if l["y0"] >= top - 2 and l["y1"] <= col_bottom + 2
                         and (l["col"] == col or l["col"] is None)]
                if any(l["col"] is None and (l["x1"] - l["x0"]) > 1.35 * cw
                       for l in probe):
                    col = None

            cb = (lay["content_left"], lay["content_right"]) if col is None \
                else rec.column_bounds(lay["columns"], col, lay["w"], 10)
            if col is None:
                bottom = bottom_any
            else:
                bottom = col_bottom
            if bottom - top < 22:
                continue
            reg = region_of(lay["lines"], lay["images"], top, bottom, cb, col)
            if reg is None:
                continue

            x0, y0, x1, y1 = reg["rect"]
            clip = pymupdf.Rect(
                max(cb[0] - 4, x0 - 10), max(0, y0 - 6),
                min(cb[1] + 4, x1 + 12), min(lay["h"], y1 + 8))
            name = crop_name(pno, a["qno"])
            doc[pno - 1].get_pixmap(dpi=args.dpi, clip=clip).save(
                os.path.join(crops_dir, name))
            full_text = reg["text"]
            stem_text = re.split(
                r"【\s*(?:答案|解答|解析|分析|点评)\s*】|(?:答案|解答|解析)\s*[:：]",
                full_text)[0].strip() or full_text
            sec = sec_by_idx.get(a["line_index"]) or ""
            has_hint = bool(QUESTION_HINT_RE.search(
                lay["ordered"][a["line_index"]]["text"]))
            looks_def = (len(stem_text) < 80 and not has_hint
                         and bool(DEFINITION_RE.search(stem_text)))
            likely = not ((re.search(r"知识|方法|考点", sec) and not has_hint)
                          or looks_def)
            questions.append({
                "qid": f"Q{len(questions) + 1:03d}",
                "qno": a["qno"], "page": pno, "column": col,
                "page_w": round(lay["w"], 1), "page_h": round(lay["h"], 1),
                "rect": [round(v, 1) for v in clip],
                "crop": os.path.join(crops_dir, name).replace("\\", "/"),
                "text": stem_text[:600],
                "text_full": full_text[:1200],
                "section": sec,
                "likely_question": likely,
                "continues_to": None,
                "continues_to_column": None,
            })

            # —— 跨栏延续：本栏最后一题触底，下一栏顶部还有无编号内容 ——
            ncols = len(lay["columns"])
            if ncols and col is not None and col < ncols - 1 and not same_col \
                    and bottom >= rec.column_bottom(lay["lines"], col) - 6:
                next_col = col + 1
                right_anchors = [x for x in lay["anchors"] if x["col"] == next_col]
                cut_y = right_anchors[0]["y0"] - 3 if right_anchors else FOOTER_Y
                cont = [l for l in lay["lines"]
                        if l["col"] == next_col and l["y1"] <= cut_y
                        and not SEC_RE.match(l["text"])]
                cont_imgs = [g for g in lay["images"]
                             if g["col"] == next_col and g["y1"] <= cut_y]
                if cont or cont_imgs:
                    ch = max([l["y1"] for l in cont] + [g["y1"] for g in cont_imgs],
                             default=HEADER_Y) - HEADER_Y
                    if ch >= 25:
                        questions[-1]["continues_to_column"] = next_col
                        warns.append(f"⚠ 第{pno}页 题{a['qno']} 可能跨到第{next_col+1}栏"
                                     f"（延续高度 {ch:.0f}pt）")
                        if args.merge:
                            cb2 = lay["columns"][next_col]
                            y0n = min([l["y0"] for l in cont] + [g["y0"] for g in cont_imgs])
                            y1n = max([l["y1"] for l in cont] + [g["y1"] for g in cont_imgs])
                            x0n = min([l["x0"] for l in cont] + [g["x0"] for g in cont_imgs])
                            x1n = max([l["x1"] for l in cont] + [g["x1"] for g in cont_imgs])
                            clip2 = pymupdf.Rect(max(cb2[0] - 4, x0n - 10),
                                                 max(HEADER_Y, y0n - 4),
                                                 min(cb2[1] + 4, x1n + 12),
                                                 min(FOOTER_Y, y1n + 6))
                            mname = crop_name(pno, a["qno"], "_合并")
                            merge_clips(doc, pno - 1, clip, pno - 1, clip2,
                                        os.path.join(crops_dir, mname), args.dpi)
                            questions[-1]["crop_merged"] = \
                                os.path.join(crops_dir, mname).replace("\\", "/")

            # —— 跨页延续：本题触底且下一页首个锚点前还有正文 ——
            touches_bottom = (bottom >= lay["content_bottom"] - 6)
            nxt = per_page.get(pno + 1)
            starts_answer = bool(answer_from and pno + 1 == answer_from[0])
            if touches_bottom and nxt and not starts_answer:
                first_anchor_y = nxt["anchors"][0]["y0"] if nxt["anchors"] else FOOTER_Y
                cont_lines = [l for l in nxt["ordered"]
                              if l["y1"] <= first_anchor_y - 3
                              and not SEC_RE.match(l["text"])]
                cont_imgs = [g for g in nxt["images"] if g["y1"] <= first_anchor_y - 3]
                cont_h = max([l["y1"] for l in cont_lines] +
                             [g["y1"] for g in cont_imgs], default=HEADER_Y) - HEADER_Y
                if cont_lines or cont_imgs:
                    if cont_h >= 25:
                        questions[-1]["continues_to"] = pno + 1
                        warns.append(f"⚠ 第{pno}页 题{a['qno']} 可能跨到第{pno+1}页"
                                     f"（延续高度 {cont_h:.0f}pt）")
                        if args.merge:
                            y0n = min([l["y0"] for l in cont_lines] +
                                      [g["y0"] for g in cont_imgs])
                            y1n = max([l["y1"] for l in cont_lines] +
                                      [g["y1"] for g in cont_imgs])
                            xn0 = min([l["x0"] for l in cont_lines] +
                                      [g["x0"] for g in cont_imgs])
                            xn1 = max([l["x1"] for l in cont_lines] +
                                      [g["x1"] for g in cont_imgs])
                            clip2 = pymupdf.Rect(max(18, xn0 - 10), max(HEADER_Y, y0n - 4),
                                                 min(nxt["w"] - 18, xn1 + 12),
                                                 min(FOOTER_Y, y1n + 6))
                            mname = crop_name(pno, a["qno"], "_合并")
                            merge_clips(doc, pno - 1, clip, pno, clip2,
                                        os.path.join(crops_dir, mname), args.dpi)
                            questions[-1]["crop_merged"] = \
                                os.path.join(crops_dir, mname).replace("\\", "/")

    # ---- 答案区：单独解析为 answers.json，绝不再混入题目 ----
    if answer_from:
        ap_pg, ap_y = answer_from
        expected = 1   # 答案题号从 1 起递增，用于过滤小数/数值误判
        for pno in sorted(per_page):
            if pno < ap_pg:
                continue
            lay = per_page[pno]
            page = doc[pno - 1]
            cur = None
            for ln in lay["ordered"]:
                if pno == ap_pg and ln["y0"] < ap_y - 2:
                    continue
                t = ln["text"].strip()
                flat = re.sub(r"\s+", "", t)
                if not t or (len(flat) <= 16 and ANSWER_HEAD_RE.match(flat)):
                    continue
                marks = []
                for m in ANS_MARK_RE.finditer(t):
                    qno = int(m.group(1))
                    if qno == expected or (expected < qno <= expected + 3) \
                            or (qno == 1 and expected > 1):
                        marks.append(m)
                        expected = qno + 1
                if not marks:
                    if cur is not None:   # 无编号行 → 视为上一条答案的续行
                        cur["text"] = (cur["text"] + " " + t)[:600]
                    continue
                for k, m in enumerate(marks):
                    start = m.end()
                    end = marks[k + 1].start() if k + 1 < len(marks) else len(t)
                    seg = t[start:end].strip(" \t．.、:：;；")
                    if not seg:
                        continue
                    x0, y0, x1, y1 = ln["bbox"]
                    clip = pymupdf.Rect(max(18, x0 - 10), max(0, y0 - 4),
                                        min(lay["w"] - 18, x1 + 12),
                                        min(lay["h"], y1 + 6))
                    name = crop_name(pno, int(m.group(1)), prefix="a")
                    page.get_pixmap(dpi=args.dpi, clip=clip).save(
                        os.path.join(crops_dir, name))
                    cur = {"qno": int(m.group(1)), "page": pno, "text": seg[:600],
                           "rect": [round(v, 1) for v in clip],
                           "crop": os.path.join(crops_dir, name).replace("\\", "/")}
                    answers.append(cur)

    # ---- 题号链诊断 ----
    qnos = [q["qno"] for q in questions]
    diag = []
    for a, b in zip(qnos, qnos[1:]):
        if b == a:
            diag.append(f"题号重复: {a}")
        elif b < a and b != 1:
            diag.append(f"题号回退: {a} -> {b}（检查是否编号错乱或按题型重新编号）")

    with open(os.path.join(args.out, "questions.json"), "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=1)
    if answer_from:
        with open(os.path.join(args.out, "answers.json"), "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(f"文件: {args.pdf}\n")
        f.write(f"切出题目: {len(questions)} 张\n")
        n_know = sum(1 for q in questions if not q.get("likely_question", True))
        if n_know:
            f.write(f"其中疑似知识条目/非题目: {n_know} 条（likely_question=false，检索/盲解默认跳过）\n")
        cols = {p: len(per_page[p]["columns"]) for p in per_page if per_page[p]["columns"]}
        if cols:
            f.write("版面: " + "，".join(f"第{p}页{cols[p]}栏" for p in sorted(cols)) + "\n")
        if answer_from:
            f.write(f"答案区: 从第{answer_from[0]}页起（已从题目中排除），"
                    f"检出答案 {len(answers)} 条\n")
        f.write("题号诊断:\n")
        f.write("\n".join("  - " + d for d in diag) if diag else "  （无异常）")
        f.write("\n")
        if layout_warns:
            f.write("版面诊断:\n" + "\n".join("  - " + w for w in layout_warns) + "\n")
        if warns:
            f.write("\n".join(warns) + "\n")

    print(f"切出题目: {len(questions)} 张 → {os.path.join(args.out, 'crops')}")
    n_know = sum(1 for q in questions if not q.get("likely_question", True))
    if n_know:
        print(f"其中疑似知识条目/非题目: {n_know} 条（已标注，检索/盲解默认跳过）")
    if answer_from:
        print(f"答案区: 从第{answer_from[0]}页起，检出答案 {len(answers)} 条 "
              f"→ {os.path.join(args.out, 'answers.json')}")
    if diag:
        print("题号诊断:", *diag, sep="\n  - ")
    for w in layout_warns:
        print(w)
    for w in warns:
        print(w)
    print(f"清单: {os.path.join(args.out, 'questions.json')}")


if __name__ == "__main__":
    main()
