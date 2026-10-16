# -*- coding: utf-8 -*-
"""盲解结果比对器（P1-7 第二解题者 · 下半场）
=====================================================
把"盲解者答案"与"官方/现有答案"逐题比对：
  一致 → 双证据通过；
  不一致 → 列为"存疑"，交人工第三遍复核（绝不直接判官方错）。

用法:
  python compare_answers.py --official official.json --solver solver_answers.json -o cmp_out
  两个文件都接受两种格式：
    {"5": "10、8/3、2/9", "6": "D"}
    或 [{"qno": 5, "answer": "10、8/3、2/9"}, ...]
输出:
  cmp_out/comparison.md    人读对比表
  cmp_out/comparison.json  机器可读（discrepancies 供报告 level=doubt 使用）
"""
import argparse
import json
import os
import re
import sys
from fractions import Fraction

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_answers(path):
    data = json.load(open(path, encoding="utf-8-sig"))
    out = {}
    if isinstance(data, dict):
        for k, v in data.items():
            out[str(k).strip()] = str(v).strip()
    elif isinstance(data, list):
        for it in data:
            out[str(it.get("qno")).strip()] = str(it.get("answer", "")).strip()
    return out


def norm_text(s):
    s = str(s).strip()
    s = re.sub(r"^(答案|答)\s*[:：]\s*", "", s)
    tr = {"（": "(", "）": ")", "，": ",", "、": ",", "：": ":",
          "；": ";", "．": ".", "　": "", "或": ",", "／": "/"}
    for a, b in tr.items():
        s = s.replace(a, b)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^x=", "", s)          # x=5 → 5
    s = re.sub(r"^[ABCDABCD]$", lambda m: m.group(0).upper(), s)
    return s


def as_number(tok):
    """尝试解析为数值/分数：'8/3' '10' '0.5' '−2' '-2'"""
    t = tok.replace("−", "-").replace("^", "")
    t = t.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return Fraction(t)
    if re.fullmatch(r"-?\d+/\d+", t):
        return Fraction(t)
    if t.startswith("-") and re.fullmatch(r"-?\d+/\d+", t[1:]):
        return Fraction(t)
    return None


def loose_eq(a, b):
    na, nb = norm_text(a), norm_text(b)
    if na == nb:
        return "一致"
    # 集合式多解：按 ,/; 分隔后逐个比
    sa = [t for t in re.split(r"[,;]", na) if t]
    sb = [t for t in re.split(r"[,;]", nb) if t]
    if sa and sb:
        seta, setb = set(sa), set(sb)
        if seta == setb:
            return "一致(多解顺序不同)"
        # 数值等价
        fa = [as_number(t) for t in seta]
        fb = [as_number(t) for t in setb]
        if all(x is not None for x in fa) and all(x is not None for x in fb) \
           and sorted(fa) == sorted(fb):
            return "一致(数值等价)"
    # 单值数值等价
    va, vb = as_number(na), as_number(nb)
    if va is not None and vb is not None and va == vb:
        return "一致(数值等价)"
    # 选择题：B(2) vs B
    ra, rb = re.match(r"^([A-D])", na), re.match(r"^([A-D])", nb)
    if ra and rb and ra.group(1) == rb.group(1):
        return "一致(选项字母相同)"
    return None


def main():
    ap = argparse.ArgumentParser(description="盲解结果比对器")
    ap.add_argument("--official", required=True)
    ap.add_argument("--solver", required=True)
    ap.add_argument("-o", "--out", default="cmp_out")
    args = ap.parse_args()

    off = load_answers(args.official)
    sol = load_answers(args.solver)
    os.makedirs(args.out, exist_ok=True)

    rows, discrepancies = [], []
    common = sorted(set(off) & set(sol), key=lambda x: (len(x), x))
    for q in common:
        verdict = loose_eq(off[q], sol[q])
        ok = verdict is not None
        rows.append((q, off[q], sol[q], verdict or "❌ 不一致"))
        if not ok:
            discrepancies.append({"qno": q, "official": off[q], "solver": sol[q]})
    only_off = sorted(set(off) - set(sol), key=lambda x: (len(x), x))
    only_sol = sorted(set(sol) - set(off), key=lambda x: (len(x), x))

    md = ["# 盲解交叉验证报告", "",
          f"比对题目: {len(common)}　一致: {len(common) - len(discrepancies)}　不一致: {len(discrepancies)}",
          ""]
    md.append("| 题号 | 官方/现有答案 | 盲解者答案 | 判定 |")
    md.append("|---|---|---|---|")
    for q, o, s, v in rows:
        md.append(f"| {q} | {o} | {s} | {v} |")
    if discrepancies:
        md.append("")
        md.append("## ⚠ 不一致（列入「存疑」，请第三遍人工复核；不得直接判官方错）")
        for d in discrepancies:
            md.append(f"- 题{d['qno']}：官方「{d['official']}」 vs 盲解「{d['solver']}」")
    if only_off:
        md.append("")
        md.append(f"（仅有官方答案、盲解未作答：{', '.join(only_off)}）")
    if only_sol:
        md.append(f"（盲解多出、官方没有：{', '.join(only_sol)}）")
    open(os.path.join(args.out, "comparison.md"), "w", encoding="utf-8").write("\n".join(md))
    json.dump({"consistent": len(common) - len(discrepancies),
               "discrepancies": discrepancies,
               "only_official": only_off, "only_solver": only_sol},
              open(os.path.join(args.out, "comparison.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"比对 {len(common)} 题：一致 {len(common) - len(discrepancies)}，不一致 {len(discrepancies)}")
    for d in discrepancies:
        print(f"  ⚠ 题{d['qno']}: 官方「{d['official']}」 vs 盲解「{d['solver']}」 → 存疑，待第三遍复核")
    print(f"报告: {os.path.join(args.out, 'comparison.md')}")


if __name__ == "__main__":
    main()
