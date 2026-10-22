# -*- coding: utf-8 -*-
"""本地题目 vs 检索到的原题：差异定位（只给线索，不判对错）
=====================================================
题目允许改编：换数/换情境/换问法都正常，**与原题不同不是错误**。
本脚本只把差异分成 `info`（版本/文字）与 `check`（数字/条件变化，需按本地题重算），
答案正确性交给 verify_answer.py / 独立求解。

用法:
  python diff_question.py --originals 输出/search/search_results.json -o 输出/diff
  python diff_question.py --local-text "..." --original-text "..."      # 单条对比

输出:
  diff/diff_results.json   机器可读（供 make_review.py / AI 使用）
  diff/diff_report.md      人读表格

判定纪律:
  题目改编≠错误。差异只用于提醒"本地题可能与常见版本不同"，必须按本地题重算；
  答案是否正确用 verify_answer.py 验证，绝不因文本不同直接判错。
"""
import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
OP_RE = re.compile(r"[+\-*/=<>≤≥≠±×÷]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
PUNCT_MAP = {"（": "(", "）": ")", "，": ",", "、": ",", "：": ":", "；": ";",
             "．": ".", "。": ".", "？": "?", "！": "!", "－": "-", "−": "-",
             "×": "*", "÷": "/", "≤": "<=", "≥": ">=", "≠": "!=", "　": " "}


def normalize(s):
    s = s or ""
    for a, b in PUNCT_MAP.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^(\d{1,3})[.、]", "", s)      # 开头题号
    return s


def question_part(text):
    """只保留题干+选项：去掉开头的题号，截掉答案/解析区。"""
    s = text or ""
    s = re.split(r"【?\s*(?:参考)?答案\s*】?|【解析】|【解答】|解析[:：]|解答[:：]|"
                 r"考点[:：]|分析[:：]|点评[:：]", s)[0]
    s = re.sub(r"^\s*\d{1,3}\s*[.．、]\s*", "", s)
    return s.strip()


def numbers_with_pos(text):
    return [(m.group(), m.start()) for m in NUM_RE.finditer(normalize(text))]


def option_numbers(text):
    vals = set()
    for seg in re.findall(r"[A-DＡ-Ｄ]\s*[.．、]\s*([^A-DＡ-Ｄ]+)", text or ""):
        vals.update(NUM_RE.findall(normalize(seg)))
    return vals


def char_kind(ch):
    if ch.isdigit():
        return "number"
    if CJK_RE.match(ch):
        return "cjk"
    if OP_RE.match(ch):
        return "operator"
    if ch.isalpha():
        return "latin"
    return "punct"


def classify_replace(a, b):
    ka, kb = char_kind(a), char_kind(b)
    if ka == "number" or kb == "number":
        return "number"
    if ka == "operator" or kb == "operator":
        return "operator"
    if ka == "cjk" and kb == "cjk":
        return "cjk"
    return "punct"


def diff_spans(local, original):
    a, b = normalize(local), normalize(original)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    spans = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        la, ob = a[i1:i2], b[j1:j2]
        kind = classify_replace(la[:1], ob[:1]) if op == "replace" else (
            "missing" if op == "delete" else "extra")
        spans.append({"op": op, "local": la, "original": ob, "kind": kind,
                      "local_pos": i1, "original_pos": j1})
    return spans, sm.ratio()


def pick_relevant(fetched, local, max_len=1200):
    """从抓取页正文里挑与本地题干最相关的一段。"""
    if not fetched:
        return ""
    blocks = [b.strip() for b in re.split(r"[\n。；;]", fetched) if len(b.strip()) >= 8]
    if not blocks:
        return fetched[:max_len]
    best, best_score = "", 0.0
    target = normalize(local)
    for i, b in enumerate(blocks):
        cand = "".join(blocks[max(0, i - 1):i + 2])
        sc = SequenceMatcher(None, normalize(b), target, autojunk=False).ratio()
        if sc > best_score:
            best, best_score = cand, sc
    return best[:max_len]


def assess(local, original):
    lq, oq = question_part(local), question_part(original)
    spans, ratio = diff_spans(lq, oq)
    na, nb = normalize(lq), normalize(oq)
    # 共同前缀之外的数字视为"原题尾部补充（答案/后续设问）"，不判为关键差异
    prefix = 0
    for x, y in zip(na, nb):
        if x != y:
            break
        prefix += 1
    exhausted = len(na) <= prefix + 2   # 本地题干在差异点附近就结束了 → 原题后面多半是答案
    if exhausted:
        nl = {t for t, p in numbers_with_pos(lq) if p < prefix}
        no = {t for t, p in numbers_with_pos(oq) if p < prefix}
        tail_o = {t for t, p in numbers_with_pos(oq) if p >= prefix}
    else:
        nl = {t for t, p in numbers_with_pos(lq) if p <= prefix}
        no = {t for t, p in numbers_with_pos(oq) if p <= prefix}
        tail_o = {t for t, p in numbers_with_pos(oq) if p > prefix}
    issues = []

    if nl != no:
        miss, extra = sorted(nl - no), sorted(no - nl)
        issues.append({
            "level": "info", "type": "数字不同（可能改编）",
            "desc": f"本地题干数字 {sorted(nl)}；原题题干数字 {sorted(no)}",
            "missing_in_original": miss, "extra_in_original": extra,
        })
    elif tail_o - {t for t, _ in numbers_with_pos(lq)}:
        issues.append({"level": "info", "type": "原题尾部含答案/补充",
                       "desc": "原题在题干之后还有数字内容（多为答案或后续设问），未纳入比对"})
    # 选项值单独看（不计入高优先，很多版本选项顺序/数值本就不同）
    ol, oo = option_numbers(lq), option_numbers(oq)
    if ol and oo and ol != oo:
        issues.append({"level": "info", "type": "选项值不同",
                       "desc": "选项数值有差异，可能为改编版本；请按本地题核对"})
    op_l = set(OP_RE.findall(na))
    op_o = set(OP_RE.findall(nb))
    if op_l != op_o:
        issues.append({"level": "check", "type": "运算符/条件不同",
                       "desc": f"本地 {sorted(op_l)}；原题 {sorted(op_o)}（按本地题重算）"})

    repl_cjk = [s for s in spans if s["kind"] == "cjk"]
    repl_num = [s for s in spans if s["kind"] == "number"]
    if repl_cjk and not repl_num:
        issues.append({
            "level": "info", "type": "文字表述不同（可能改编）",
            "desc": "；".join(f"本地「{s['local']}」→ 原题「{s['original']}」"
                             for s in repl_cjk[:6]),
        })
    if spans and not issues:
        issues.append({"level": "info", "type": "标点/格式差异",
                       "desc": f"{len(spans)} 处字符差异，不影响题意"})

    gap = abs(len(na) - len(nb))
    if gap > max(12, 0.25 * len(na)):
        issues.append({"level": "info", "type": "长度差异大（可能改编）",
                       "desc": f"本地 {len(na)} 字，原题 {len(nb)} 字"})

    only_tail = bool(spans) and all(
        s["op"] == "insert" and s["local_pos"] >= max(0, len(na) - 1) for s in spans)

    if any(i["level"] == "check" for i in issues):
        verdict = "条件/数字有变化（按本地题重算）"
    elif not issues or (only_tail and all(i["level"] == "info" for i in issues)):
        verdict = "实质一致（可能仅表述不同）"
    elif ratio >= 0.80:
        verdict = "版本差异（题目可能改编，非错误）"
    elif ratio >= 0.55:
        verdict = "改编较大（可能非同题）"
    else:
        verdict = "低相似（不足以作为证据）"

    return {"similarity": round(ratio, 3), "verdict": verdict,
            "issues": issues, "diff": spans,
            "local_norm": na, "original_norm": nb,
            "decision": "pending_ai_review"}


def main():
    ap = argparse.ArgumentParser(description="本地题目与原题差异定位")
    ap.add_argument("--originals", help="search_original.py 的 search_results.json")
    ap.add_argument("--local-text")
    ap.add_argument("--original-text")
    ap.add_argument("-o", "--out", default="diff_out")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    if args.local_text and args.original_text:
        res = assess(args.local_text, args.original_text)
        res.update({"qid": "Q001", "qno": 1, "local_text": args.local_text,
                    "original_text": args.original_text})
        print(json.dumps(res, ensure_ascii=False, indent=1))
        json.dump({"items": [res]}, open(os.path.join(args.out, "diff_results.json"),
                                        "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return

    if not args.originals:
        sys.exit("请提供 --originals，或同时提供 --local-text/--original-text")

    data = json.load(open(args.originals, encoding="utf-8-sig"))
    items, md = [], ["# 原题差异报告", "",
                     "> **题目允许改编**：与原题不同 ≠ 错误。本报告只列差异线索；"
                     "正确性以本地题目重算 + 答案等价验证为准。", ""]
    md.append("| 题 | 相似度 | 结论 | 主要差异 | 原题链接 |")
    md.append("|---|---|---|---|---|")
    for it in data.get("items", []):
        local = it.get("local_text", "")
        results = it.get("results") or []
        if not results:
            items.append({"qid": it.get("qid"), "qno": it.get("qno"),
                          "page": it.get("page"), "local_text": local,
                          "verdict": "未检索到候选", "similarity": 0.0,
                          "issues": [], "diff": []})
            continue
        # 优先抓取正文，其次摘要
        best = max(results, key=lambda r: r.get("score", 0))
        orig = pick_relevant(best.get("fetched_text", ""), local) \
            or best.get("snippet") or best.get("title", "")
        res = assess(local, orig)
        res.update({"qid": it.get("qid"), "qno": it.get("qno"), "page": it.get("page"),
                    "local_text": local, "original_text": orig,
                    "source": {"url": best.get("url"), "title": best.get("title"),
                               "provider": best.get("source"),
                               "score": best.get("score", 0)}})
        items.append(res)
        main_issue = "；".join(f"{i['type']}: {i['desc']}" for i in res["issues"][:2]) or "无"
        md.append(f"| {res['qno']} | {res['similarity']:.2f} | {res['verdict']} | "
                  f"{main_issue[:80]} | {best.get('url', '')} |")

    json.dump({"generated": data.get("generated"), "items": items},
              open(os.path.join(args.out, "diff_results.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    open(os.path.join(args.out, "diff_report.md"), "w", encoding="utf-8").write(
        "\n".join(md) + "\n")

    # 给 AI 的判定任务书：脚本只列证据，结论必须由模型/人给出
    tasks = ["# 原题差异判定任务（交给 AI 逐题判定）", "",
             "对每题只输出一个 JSON 对象，字段：",
             '`{"qid": "Q003", "conclusion": "adapted_ok|local_logic_error|local_answer_error|uncertain", '
             '"reason": "……", "evidence": ["……"], "confidence": "high|medium|low"}`', "",
             "判定口径（题目允许改编）：",
             "- `adapted_ok`：与网上原题不同，但本地题目逻辑自洽、可解，答案正确；",
             "- `local_logic_error`：本地题目条件矛盾、缺条件、图文不符或无解；",
             "- `local_answer_error`：本地答案数学上错误（必须先用 verify_answer.py 独立验证）；",
             "- `uncertain`：证据不足，列🟠存疑。", "",
             "**禁止**仅凭“与网上不一样”就判错；题目可以换数/换情境/换问法。", ""]
    for x in items:
        if not x.get("diff") and not x.get("issues"):
            continue
        tasks += [f"## {x.get('qid') or ('第' + str(x['qno']) + '题')}"
                  f"（原题号 {x['qno']}，第{x.get('page') or '?'}页，相似度 {x.get('similarity', 0):.2f}）",
                  f"- 本地：{x.get('local_text', '')[:300]}",
                  f"- 原题：{x.get('original_text', '')[:300]}"]
        for i in x.get("issues", []):
            tasks.append(f"- 差异线索（{i['type']}）：{i['desc'][:200]}")
        if x.get("source", {}).get("url"):
            tasks.append(f"- 来源：{x['source']['url']}")
        tasks.append("")
    open(os.path.join(args.out, "ai_review_tasks.md"), "w", encoding="utf-8").write(
        "\n".join(tasks))

    high = sum(1 for x in items if any(i["level"] == "high" for i in x["issues"]))
    print(f"比对完成: {len(items)} 题，数字不一致 {high} 题 → "
          f"{os.path.join(args.out, 'diff_results.json')}")
    print("下一步：把这些差异交给 AI 逐条复核（脚本不替你做结论）。")


if __name__ == "__main__":
    main()
