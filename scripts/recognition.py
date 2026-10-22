# -*- coding: utf-8 -*-
"""版面识别核心（栏感知 + 阅读顺序 + 题号锚定）
=====================================================
解决试卷 PDF 识别的三个高频失真点：
  1) 双栏排版：按 y 排序会把左右栏串成一行 → 用 XY-cut 还原阅读顺序；
  2) 题号误判：选项 A. / 小题（1） / 正文数字被当成题号 → 加左边距、字号、行首约束；
  3) 图形串栏：左栏题的配图被右栏同高度图片污染 → 区域按栏裁剪。

对外 API（其它脚本只依赖这几个函数）:
  analyze_page(page)        -> dict  页面版面（lines / images / columns / anchors / order）
  detect_columns(lines, w)  -> [(x0,x1), ...] 或 []
  reading_order(lines)      -> [line, ...]   XY-cut 阅读顺序
  question_anchors(lines, columns) -> [anchor, ...]

设计取舍:
  - 纯几何 + 字体信息，不依赖深度学习，CPU 毫秒级；
  - 检测到 3 栏及以上只告警，仍按单栏/双栏近似处理（试卷极少三栏）；
  - 识别结果始终是"候选"，脚本输出 warning 提醒回图复核。
"""
import re

QN_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]\s*")
OPT_RE = re.compile(r"^\s*[A-DＡ-Ｄ]\s*[.．、]")
SUB_RE = re.compile(r"^\s*[（(]\d{1,2}[）)]")
# 栏目标题/说明行，不算跨栏正文
SEC_RE = re.compile(
    r"^\s*(?:[一二三四五六七八九十]+[、.．]|第[一二三四五六七八九十]+(?:部分|章|节)|"
    r"[◆⚫◼■●★☆※]|Part|题型|说明|【)"
)
MIN_COL_GAP = 10.0     # 栏间空白最小宽度（pt）
MIN_ROW_GAP = 9.0      # 行块切分最小垂直空白（pt）
MARGIN_TOL = 30.0      # 题号允许的左边距容差（pt）


def page_lines(page, header_y=55.0, footer_y=None, max_footer=True):
    """提取正文行（含字号/加粗/上下标信息），已剔除页眉页脚。"""
    H = page.rect.height
    if footer_y is None:
        footer_y = H - (50.0 if max_footer else 0.0)
    out = []
    blocks = page.get_text("dict")["blocks"]
    for bi, b in enumerate(blocks):
        if b.get("type") != 0:
            continue
        for li, ln in enumerate(b.get("lines", [])):
            spans = ln.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            x0, y0, x1, y1 = ln["bbox"]
            if y1 < header_y or y0 > footer_y:
                continue
            sizes = [s.get("size", 0) for s in spans if s.get("text", "").strip()]
            size = max(sizes) if sizes else 0.0
            bold = any(("bold" in s.get("font", "").lower()) or (s.get("flags", 0) & 16)
                       for s in spans)
            sup = any(s.get("flags", 0) & 1 for s in spans)
            out.append({
                "text": text, "bbox": (x0, y0, x1, y1),
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "size": round(size, 1), "bold": bold, "sup": sup,
                "block": bi, "line": li, "col": None, "order": 0,
            })
    # 初始稳定排序（同一行内按 x）
    out.sort(key=lambda l: (round(l["y0"], 1), l["x0"]))
    return out


def page_images(page, header_y=55.0, footer_y=None, min_size=8.0):
    H = page.rect.height
    if footer_y is None:
        footer_y = H - 50.0
    imgs = []
    for im in page.get_image_info():
        x0, y0, x1, y1 = im["bbox"]
        if y1 < header_y or y0 > footer_y:
            continue
        if (x1 - x0) < min_size or (y1 - y0) < min_size:
            continue
        imgs.append({"bbox": (x0, y0, x1, y1), "x0": x0, "y0": y0,
                     "x1": x1, "y1": y1, "col": None})
    return imgs


def _crossed_x(lines, page_w):
    """返回每个 x 是否被某行跨过（用于找栏间空白）。

    行尾/行首各内缩 4pt：答案或标点偶尔溢出到栏缝几个点，不应把整条栏缝堵死。
    """
    n = int(page_w) + 2
    crossed = [False] * n
    for l in lines:
        if (l["x1"] - l["x0"]) > 0.78 * page_w:   # 通栏标题不参与找缝
            continue
        a = max(0, int(l["x0"]) + 4)
        b = min(n - 1, int(l["x1"]) - 4)
        for x in range(a, b):
            crossed[x] = True
    return crossed


def detect_columns(lines, page_w, max_cols=4):
    """检测栏边界。返回 [] 表示单栏；[(x0,x1), ...] 表示 2~4 栏。"""
    sizes = sorted(l["size"] for l in lines if l["size"])
    med = sizes[len(sizes) // 2] if sizes else 10.0
    # 排除通栏标题/大字号行：它们常常横跨栏缝，会把栏缝"堵死"
    body = [l for l in lines
            if (l["x1"] - l["x0"]) < 0.78 * page_w and l["size"] <= med * 1.3
            and not SEC_RE.match(l["text"])
            and not (l["bold"] and l["size"] >= med * 1.12)]
    if len(body) < 8:
        return []
    crossed = _crossed_x(body, page_w)
    lo, hi = int(page_w * 0.08), int(page_w * 0.92)

    runs, start = [], None
    for x in range(lo, hi + 1):
        if not crossed[x]:
            if start is None:
                start = x
        elif start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, hi))
    runs = [r for r in runs if r[1] - r[0] >= MIN_COL_GAP]
    if not runs:
        return []

    # 组合栏缝：优先切出更多栏（2→4），但每栏必须有足够内容与宽度
    from itertools import combinations
    minx = min(l["x0"] for l in body)
    maxx = max(l["x1"] for l in body)
    cands = []
    for g0, g1 in runs:
        left = [l for l in body if l["x1"] <= g0 + 4]
        right = [l for l in body if l["x0"] >= g1 - 4]
        if len(left) >= 4 and len(right) >= 4:
            cands.append((g0, g1))
    for k in range(min(max_cols, len(cands) + 1), 1, -1):
        for combo in combinations(cands, k - 1):
            combo = sorted(combo)
            bounds = [minx] + [v for g in combo for v in (g[0] + 4, g[1] - 4)] + [maxx]
            segs = [(bounds[i], bounds[i + 1]) for i in range(0, len(bounds), 2)]
            if any((b - a) < 70 for a, b in segs):
                continue
            cols, ok = [], True
            for a, b in segs:
                ls = [l for l in body if l["x0"] >= a - 3 and l["x1"] <= b + 3]
                if len(ls) < 4:
                    ok = False
                    break
                cols.append((min(l["x0"] for l in ls), max(l["x1"] for l in ls)))
            if not ok:
                continue
            for a, b in zip(cols, cols[1:]):
                la = [l for l in body if l["x0"] >= a[0] - 2 and l["x1"] <= a[1] + 2]
                lb = [l for l in body if l["x0"] >= b[0] - 2 and l["x1"] <= b[1] + 2]
                if la and lb:
                    oy = min(max(l["y1"] for l in la), max(l["y1"] for l in lb)) - \
                         max(min(l["y0"] for l in la), min(l["y0"] for l in lb))
                    if oy < 60:
                        ok = False
                        break
            if ok:
                return cols
    return []


def _gaps(intervals, min_gap):
    """一维区间并集的空白段 [(start,end), ...]"""
    if not intervals:
        return []
    iv = sorted(intervals)
    merged = [list(iv[0])]
    for a, b in iv[1:]:
        if a <= merged[-1][1] + 0.5:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(merged[i][1], merged[i + 1][0])
            for i in range(len(merged) - 1)
            if merged[i + 1][0] - merged[i][1] >= min_gap]


def reading_order(lines, depth=0):
    """XY-cut 阅读顺序：先水平切（去页眉/通栏标题），再垂直切（分栏）。"""
    if len(lines) <= 1 or depth > 6:
        return sorted(lines, key=lambda l: (round(l["y0"], 1), l["x0"]))

    hg = _gaps([(l["y0"], l["y1"]) for l in lines], MIN_ROW_GAP)
    if hg:
        # 取最靠上且足够宽的横缝，保证标题/题组顺序
        cut = max(hg, key=lambda g: g[1] - g[0])[0]
        top = [l for l in lines if l["y1"] <= cut + 0.5]
        bot = [l for l in lines if l["y0"] >= cut - 0.5]
        if top and bot:
            return reading_order(top, depth + 1) + reading_order(bot, depth + 1)

    vg = _gaps([(l["x0"], l["x1"]) for l in lines], MIN_COL_GAP)
    if vg:
        cut = max(vg, key=lambda g: g[1] - g[0])[0]
        left = [l for l in lines if l["x1"] <= cut + 0.5]
        right = [l for l in lines if l["x0"] >= cut - 0.5]
        if left and right and len(left) + len(right) >= 0.6 * len(lines):
            return reading_order(left, depth + 1) + reading_order(right, depth + 1)

    return sorted(lines, key=lambda l: (round(l["y0"], 1), l["x0"]))


def assign_columns(lines, columns):
    if not columns:
        for l in lines:
            l["col"] = 0
        return
    for l in lines:
        # 跨过任意栏缝 → 通栏行
        if any(l["x0"] < columns[i][1] - 2 and l["x1"] > columns[i + 1][0] + 2
               for i in range(len(columns) - 1)):
            l["col"] = None
            continue
        best, best_ov = None, 0.0
        for i, (c0, c1) in enumerate(columns):
            ov = max(0.0, min(l["x1"], c1) - max(l["x0"], c0))
            if ov > best_ov:
                best, best_ov = i, ov
        l["col"] = best


def _left_margins(lines, columns):
    """各栏正文左边距（取 20% 分位，避开缩进段落）。"""
    if not columns:
        xs = sorted(l["x0"] for l in lines)
        return [xs[max(0, int(len(xs) * 0.2))] if xs else 0]
    margins = []
    for c in range(len(columns)):
        xs = sorted(l["x0"] for l in lines if l["col"] == c)
        margins.append(xs[max(0, int(len(xs) * 0.2))] if xs else columns[c][0])
    return margins


def question_anchors(lines, columns):
    """题号锚点：行首数字 + 栏内左边距 + 字号合理 + 非选项/非小题。"""
    margins = _left_margins(lines, columns)
    anchors = []
    for i, l in enumerate(lines):
        t = l["text"]
        if OPT_RE.match(t) or SUB_RE.match(t):
            continue
        m = QN_RE.match(t)
        if not m:
            continue
        qno = int(m.group(1))
        if qno < 1:
            continue
        if t[m.end():m.end() + 1].isdigit():   # 0.000007 这类小数，不是题号
            continue
        col = l["col"]
        if col is None:          # 通栏行里的编号不作为题号（多为标题/说明）
            continue
        margin = margins[col] if col < len(margins) else 0
        if l["x0"] > margin + MARGIN_TOL:
            continue
        if l["size"] and (l["size"] < 6.5 or l["size"] > 22):
            continue
        rest = t[m.end():].strip()
        if not rest:
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if nxt is None or nxt["col"] != col or nxt["y0"] - l["y1"] > 32:
                continue
            if SEC_RE.match(nxt["text"]):
                continue
            # 纯数字行只有在下一行是正文（中文/括号）时才算题号；
            # 公式碎片（"5．" 下一行是 "m−1"）要排除
            if not re.match(r"^[\u4e00-\u9fff（(]", nxt["text"].strip()):
                continue
        else:
            # 答案里的"5．；"这类行不是题号
            if rest[0] in "；;，,。.、:：)）":
                continue
            if len(rest) < 2:
                continue
        anchors.append({
            "qno": int(m.group(1)), "bbox": l["bbox"],
            "x0": l["x0"], "y0": l["y0"], "x1": l["x1"], "y1": l["y1"],
            "col": col, "size": l["size"], "bold": l["bold"], "line_index": i,
        })
    # 按栏索引 + 栏内 y 排序（N 栏通用）
    anchors.sort(key=lambda a: (a["col"] if isinstance(a["col"], int) else 99, a["y0"]))
    return anchors


def analyze_page(page, header_y=55.0, footer_y=None):
    lines = page_lines(page, header_y, footer_y)
    images = page_images(page, header_y, footer_y)
    columns = detect_columns(lines, page.rect.width)
    assign_columns(lines, columns)
    assign_columns(images, columns)
    ordered = reading_order([l for l in lines])
    for idx, l in enumerate(ordered):
        l["order"] = idx
    anchors = question_anchors(ordered, columns)

    warnings = []
    if not lines:
        warnings.append("本页无文本层（扫描/图片页），需 OCR 或人工看图")
    if not columns and len(lines) >= 30:
        # 双栏漏检的强证据：存在大量"从右半页起笔"的短行，且与左侧纵向重叠
        left = [l for l in lines if l["x0"] < page.rect.width * 0.22]
        right = [l for l in lines if l["x0"] > page.rect.width * 0.42
                 and (l["x1"] - l["x0"]) < 0.55 * page.rect.width]
        if len(left) > 0.30 * len(lines) and len(right) > 0.15 * len(lines):
            xs = sorted(l["x0"] for l in right)
            med = xs[len(xs) // 2]
            clustered = sum(1 for x in xs if abs(x - med) <= 25)
            ly = (min(l["y0"] for l in left), max(l["y1"] for l in left))
            ry = (min(l["y0"] for l in right), max(l["y1"] for l in right))
            if clustered > 0.6 * len(right) and \
                    min(ly[1], ry[1]) - max(ly[0], ry[0]) > 100:
                warnings.append("疑似多栏但未检出栏缝，建议人工确认版面")
    tiny = [l for l in lines if l["size"] and l["size"] < 5.5]
    if tiny:
        warnings.append(f"存在 {len(tiny)} 行超小字号（<5.5pt），可能是上下标/公式碎片")
    qnums = [a["qno"] for a in anchors]
    for a, b in zip(qnums, qnums[1:]):
        if b == a:
            warnings.append(f"题号重复: {a}（同页同栏连续出现）")

    return {
        "width": page.rect.width, "height": page.rect.height,
        "w": page.rect.width, "h": page.rect.height,
        "lines": lines, "images": images,
        "columns": columns, "anchors": anchors,
        "ordered": ordered, "warnings": warnings,
        "text": "\n".join(l["text"] for l in ordered),
    }


def column_bottom(lines, col):
    ys = [l["y1"] for l in lines if l["col"] == col]
    return max(ys) if ys else 0.0


def column_bounds(columns, col, page_w, margin=18.0):
    if columns:
        return columns[col]
    return (margin, page_w - margin)


def _template_applies(lines, template, page_w):
    """模板栏位是否适用于本页：栏缝基本无穿越、每栏都有内容。"""
    bodyish = [l for l in lines if (l["x1"] - l["x0"]) < 0.9 * page_w]
    if len(bodyish) < 8:
        return False
    for i in range(len(template) - 1):
        g0, g1 = template[i][1], template[i + 1][0]
        crossing = [l for l in bodyish
                    if l["x0"] < g0 - 4 and l["x1"] > g1 + 4]
        if len(crossing) > max(2, int(0.03 * len(bodyish))):
            return False
    for c0, c1 in template:
        inside = [l for l in bodyish
                  if c0 - 4 <= (l["x0"] + l["x1"]) / 2 <= c1 + 4]
        if len(inside) < 3:
            return False
    return True


def _apply_template(lines, images, template):
    assign_columns(lines, template)
    assign_columns(images, template)
    return template


def document_template(doc, header_y=55.0, max_pages=60):
    """从整份文档估计"主栏位"（多栏答案卷常见每页栏宽略有差异）。"""
    n = len(doc)
    if n == 0:
        return None
    step = max(1, n // max_pages)
    idxs = list(range(0, n, step))[:max_pages]
    counts, stacks = {}, []
    for i in idxs:
        lines = page_lines(doc[i], header_y)
        cols = detect_columns(lines, doc[i].rect.width)
        if cols:
            counts[len(cols)] = counts.get(len(cols), 0) + 1
            stacks.append(cols)
    if not counts:
        return None
    mode = max(counts, key=counts.get)
    if mode < 2 or counts[mode] < max(2, len(idxs) * 0.25):
        return None
    same = [c for c in stacks if len(c) == mode]
    template = []
    for i in range(mode):
        x0 = sorted(c[i][0] for c in same)[len(same) // 2]
        x1 = sorted(c[i][1] for c in same)[len(same) // 2]
        template.append((x0, x1))
    return template


def analyze_document(doc, header_y=55.0, footer_y=None, pages=None):
    """逐页分析；栏检测不稳的页用文档主栏位兜底。"""
    tpl = document_template(doc, header_y)
    out = []
    for i, page in enumerate(doc):
        if pages and (i + 1) not in pages:
            out.append(None)
            continue
        lay = analyze_page(page, header_y, footer_y)
        if tpl and len(lay["columns"]) != len(tpl) \
                and _template_applies(lay["lines"], tpl, page.rect.width):
            lay["columns"] = _apply_template(lay["lines"], lay["images"], tpl)
            lay["anchors"] = question_anchors(lay["ordered"], tpl)
            lay["text"] = "\n".join(
                l["text"] for l in reading_order(lay["lines"]))
            lay["template_applied"] = True
        out.append(lay)
    return out
