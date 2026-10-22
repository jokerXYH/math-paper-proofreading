# -*- coding: utf-8 -*-
"""数学答案等价判定（初高中高频格式，离线、可解释）
=====================================================
用途：判断"我的答案"与"文档/官方答案"是否**数学等价**，而不是字符串相同。
覆盖：整数/分数/小数/百分数、根式、幂、方程解、解集、区间、坐标、多解顺序。
可选的 Math-Verify（LaTeX）与 SymPy 双引擎；没装依赖时退化为数值比较。

用法:
  python verify_answer.py --mine "2√3" --official "√12"
  python verify_answer.py --mine "x=5或x=-1" --official "5，-1"
  python verify_answer.py --equation "2(x-1)=x+3" --value "5"
  python verify_answer.py --solve "2(x-1)=x+3"
  python verify_answer.py --official official.json --mine mine.json -o 输出目录
  python verify_answer.py --self-test

输出:
  默认打印 JSON；批量模式写 verify_results.json + verify_report.md
  verdict: same(等价) / different(不等价) / uncertain(无法解析，需人工)

依赖（可选但强烈建议）:
  pip install sympy math-verify
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import sympy as sp
    from sympy.parsing.sympy_parser import (
        parse_expr, standard_transformations, implicit_multiplication_application,
    )
    _TRANS = standard_transformations + (implicit_multiplication_application,)
except ImportError:  # 允许无 sympy 时做数值兜底
    sp = None
    _TRANS = None

SUP = {"⁰": "**0", "¹": "**1", "²": "**2", "³": "**3", "⁴": "**4",
       "⁵": "**5", "⁶": "**6", "⁷": "**7", "⁸": "**8", "⁹": "**9",
       "⁺": "+", "⁻": "-"}
UNITS = ("平方厘米", "立方厘米", "厘米", "分米", "千米", "毫米", "平方米",
         "立方米", "cm²", "cm3", "cm2", "cm", "dm", "km", "mm", "m",
         "元", "人", "个", "度", "°", "次", "件", "本", "页", "小时", "分钟")


def _strip_units(s):
    t = s.strip()
    for u in sorted(UNITS, key=len, reverse=True):
        if t.endswith(u):
            head = t[:-len(u)].strip()
            if head and (head[-1].isdigit() or head[-1] in ")]}"):
                return head
    return t


def preprocess(s):
    """把中文试卷里的常见写法转成 SymPy 可读表达式。"""
    if s is None:
        return ""
    t = str(s).strip()
    t = t.replace("$", "").replace("\\left", "").replace("\\right", "")
    t = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", t)
    t = re.sub(r"\\sqrt\{([^{}]+)\}", r"sqrt(\1)", t)
    t = t.replace("\\times", "*").replace("\\div", "/").replace("\\cdot", "*")
    t = t.replace("\\pi", "pi").replace("\\leq", "<=").replace("\\geq", ">=")
    t = re.sub(r"\\text\{([^{}]*)\}", r"\1", t)
    # √3 / 2√3 → sqrt(3) / 2sqrt(3)（否则 sqrt3 会被解析成 s*q*r*t）
    t = re.sub(r"√\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?", r"sqrt(\1)", t)
    for k, v in SUP.items():
        t = t.replace(k, v)
    t = (t.replace("√", "sqrt").replace("∛", "cbrt")
         .replace("×", "*").replace("·", "*").replace("÷", "/")
         .replace("−", "-").replace("–", "-").replace("—", "-")
         .replace("π", "pi").replace("≤", "<=").replace("≥", ">=")
         .replace("≠", "!=").replace("^", "**"))
    # 1又1/2 → (1+1/2)
    t = re.sub(r"(\d+)\s*又\s*(\d+/\d+)", r"(\1+\2)", t)
    # 20% → (20/100)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*[%％]", r"(\1/100)", t)
    t = re.sub(r"^[\(（]\s*[\)）]$", "", t)
    t = re.sub(r"^(?:答案|答)\s*[:：]\s*", "", t)
    t = re.sub(r"^[xXyYzZ]\s*=\s*", "", t)
    t = t.replace("，", ",").replace("、", ",").replace("；", ";")
    return _strip_units(t).strip()


def split_top(s):
    """按顶层 或 , ; 拆分（不拆括号/花括号里的内容）。"""
    out, buf, depth = [], "", 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in "([{（【":
            depth += 1
        elif ch in ")]}）】":
            depth -= 1
        if depth == 0 and (ch in ",;" or ch == "或"):
            out.append(buf.strip())
            buf = ""
            i += 1
            continue
        buf += ch
        i += 1
    if buf.strip():
        out.append(buf.strip())
    return [x for x in out if x]


if sp is not None:
    def to_expr(s):
        t = preprocess(s)
        if not t:
            raise ValueError("空表达式")
        return parse_expr(t, transformations=_TRANS, evaluate=True)

    def _is_zero(expr):
        try:
            if expr == 0:
                return True
            z = sp.simplify(expr)
            if z == 0:
                return True
            return bool(z.equals(0))
        except Exception:
            return False

    def _same_expr(a, b):
        try:
            if _is_zero(a - b):
                return True
        except Exception:
            pass
        try:
            if bool(a.equals(b)):
                return True
        except Exception:
            pass
        # 小数写法（2.6666666667）与分数 8/3 的近似等价
        try:
            if not a.free_symbols and not b.free_symbols:
                va, vb = complex(sp.N(a)), complex(sp.N(b))
                return abs(va - vb) <= 1e-7 * max(1.0, abs(vb))
        except Exception:
            pass
        return False

    def _numeric_same(a, b):
        syms = sorted(list(a.free_symbols | b.free_symbols), key=lambda x: x.name)
        if not syms or len(syms) > 3:
            return False
        import itertools
        for vals in itertools.product([sp.Rational(1, 2), 1, 2, 3], repeat=len(syms)):
            sub = dict(zip(syms, vals))
            try:
                if abs(complex(sp.N(a.subs(sub) - b.subs(sub)))) > 1e-9:
                    return False
            except Exception:
                return False
        return True

    def _same_equation(a, b):
        """两个等式是否同解（只比较表达式，不比较解集）。"""
        try:
            da = sp.simplify(a.lhs - a.rhs)
            db = sp.simplify(b.lhs - b.rhs)
            if _is_zero(da) and _is_zero(db):
                return True
            if _is_zero(da) or _is_zero(db):
                return False
            ratio = sp.simplify(da / db)
            return ratio.free_symbols == set() and not _is_zero(ratio)
        except Exception:
            return False

    def _bound(s):
        s = s.strip()
        if "∞" in s:
            return -sp.oo if s.startswith("-") else sp.oo
        return sp.Float(s)

    def _parse_answer(s):
        t = preprocess(s)
        if not t:
            raise ValueError("空答案")
        # 区间：a<=x<=b / [a,b] / (a,+∞)
        m = re.match(r"^(-?\d+(?:\.\d+)?)\s*<=?\s*[a-zA-Z]\s*<=?\s*(-?\d+(?:\.\d+)?)$", t)
        if m:
            return ("interval", sp.Interval(float(m.group(1)), float(m.group(2))))
        m = re.match(r"^([\[\(])\s*([-+]?∞|-?\d+(?:\.\d+)?)\s*,\s*([-+]?∞|-?\d+(?:\.\d+)?)\s*([\]\)])$", t)
        if m:
            return ("interval", sp.Interval(_bound(m.group(2)), _bound(m.group(3)),
                                            left_open=m.group(1) == "(",
                                            right_open=m.group(4) == ")"))
        # 不等式：x>2 / 2<x<=5
        m = re.match(r"^(.*?)(<=|>=|<|>)(.*)$", t)
        if m and re.search(r"[a-zA-Z]", t):
            try:
                lhs, op, rhs = m.group(1), m.group(2), m.group(3)
                rel = {"<=": sp.Le, ">=": sp.Ge, "<": sp.Lt, ">": sp.Gt}[op](
                    to_expr(lhs), to_expr(rhs))
                syms = sorted(rel.free_symbols, key=lambda x: x.name)
                if len(syms) == 1:
                    sol = sp.solve_univariate_inequality(rel, syms[0], relational=False)
                    if isinstance(sol, sp.Union):
                        return ("set", tuple(("interval", a) for a in sol.args))
                    return ("interval", sol)
            except Exception:
                pass
        t = t.strip()
        if (t.startswith("{") and t.endswith("}")) or (t.startswith("【") and t.endswith("】")):
            inner = t[1:-1]
            return ("set", tuple(_parse_answer(x) for x in split_top(inner)))
        parts = split_top(t)
        if len(parts) > 1:
            return ("set", tuple(_parse_answer(x) for x in parts))
        # 坐标 (a,b)
        m = re.match(r"^\(\s*([^,]+)\s*,\s*([^,]+)\s*\)$", t)
        if m:
            return ("tuple", (to_expr(m.group(1)), to_expr(m.group(2))))
        # 带等号的答案：x=5 / y=2x+1 / 2x+1=5
        if "=" in t and "<" not in t and ">" not in t:
            l, r = t.split("=", 1)
            return ("equation", sp.Eq(to_expr(l), to_expr(r)))
        return ("expr", to_expr(t))

    def _same_parsed(a, b):
        if a[0] != b[0]:
            # 方程 vs 解集：解方程后与集合比较（必须先于"集合 vs 单值"）
            if {a[0], b[0]} == {"equation", "set"}:
                eq, st = (a[1], b[1]) if a[0] == "equation" else (b[1], a[1])
                syms = sorted(eq.free_symbols, key=lambda x: x.name)
                if len(syms) == 1:
                    try:
                        sols = sp.solve(eq, syms[0])
                        return len(sols) == len(st) and all(
                            any(_same_parsed(("expr", x), y) for y in st) for x in sols)
                    except Exception:
                        return False
            # 集合 vs 单值：把单值当一元集合
            if a[0] == "set" or b[0] == "set":
                aa = a[1] if a[0] == "set" else (a,)
                bb = b[1] if b[0] == "set" else (b,)
                return len(aa) == len(bb) and all(
                    any(_same_parsed(x, y) for y in bb) for x in aa)
            # 方程 vs 单值：解方程后比较唯一解
            if {a[0], b[0]} == {"equation", "expr"}:
                eq, val = (a[1], b[1]) if a[0] == "equation" else (b[1], a[1])
                syms = sorted(eq.free_symbols, key=lambda x: x.name)
                if len(syms) == 1:
                    try:
                        sols = sp.solve(eq, syms[0])
                        return len(sols) == 1 and _same_expr(sols[0], val)
                    except Exception:
                        return False
            return False
        kind = a[0]
        if kind == "interval":
            ia, ib = a[1], b[1]
            try:
                return (ia.left_open == ib.left_open and ia.right_open == ib.right_open
                        and _same_expr(ia.start, ib.start) and _same_expr(ia.end, ib.end))
            except Exception:
                return ia == ib
        if kind == "tuple":
            return len(a[1]) == len(b[1]) and all(_same_expr(x, y) for x, y in zip(a[1], b[1]))
        if kind == "equation":
            if _same_equation(a[1], b[1]):
                return True
            # 不同形式但同解（一元方程）
            syms = sorted(a[1].free_symbols | b[1].free_symbols, key=lambda x: x.name)
            if len(syms) == 1:
                try:
                    sa = sp.solve(a[1], syms[0])
                    sb = sp.solve(b[1], syms[0])
                    return len(sa) == len(sb) and all(
                        any(_same_expr(x, y) for y in sb) for x in sa)
                except Exception:
                    return False
            return False
        if kind == "set":
            aa, bb = a[1], b[1]
            if len(aa) != len(bb):
                return False
            return all(any(_same_parsed(x, y) for y in bb) for x in aa)
        return _same_expr(a[1], b[1])


def _numeric_fallback(mine, official):
    """无 SymPy 时的数值兜底：分数/小数/百分数/根式近似。"""
    def val(s):
        t = preprocess(s).strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
            return float(t)
        m = re.fullmatch(r"\(?(-?\d+(?:\.\d+)?)\)?/\(?(-?\d+(?:\.\d+)?)\)?", t)
        if m:
            return float(m.group(1)) / float(m.group(2))
        m = re.fullmatch(r"\(?(-?\d+(?:\.\d+)?)\)?\*?sqrt\(?(-?\d+(?:\.\d+)?)\)?", t)
        if m:
            return float(m.group(1)) * float(m.group(2)) ** 0.5
        if re.fullmatch(r"sqrt\(?(-?\d+(?:\.\d+)?)\)?", t):
            return float(re.fullmatch(r"sqrt\(?(-?\d+(?:\.\d+)?)\)?", t).group(1)) ** 0.5
        return None

    va, vb = val(mine), val(official)
    if va is not None and vb is not None:
        return abs(va - vb) < 1e-9
    return None


def verify_answer(mine, official):
    """返回 {verdict, method, detail}；不抛异常。"""
    m, o = str(mine or "").strip(), str(official or "").strip()
    if not m or not o:
        return {"verdict": "uncertain", "method": "none", "detail": "答案为空"}
    if re.sub(r"\s+", "", m) == re.sub(r"\s+", "", o):
        return {"verdict": "same", "method": "text", "detail": "字符串一致"}

    if sp is not None:
        try:
            pa, pb = _parse_answer(m), _parse_answer(o)
            if _same_parsed(pa, pb):
                return {"verdict": "same", "method": "sympy", "detail": "符号/数值等价"}
            # 数值抽样兜底（含变量时）
            if pa[0] == pb[0] == "expr" and _numeric_same(pa[1], pb[1]):
                return {"verdict": "same", "method": "sympy-numeric",
                        "detail": "变量取值抽样等价"}
            # 近似值（如 1/3 写成 0.333）：不当等价，标存疑提醒确认保留位数
            if pa[0] == pb[0] == "expr" and not pa[1].free_symbols and not pb[1].free_symbols:
                try:
                    va, vb = complex(sp.N(pa[1])), complex(sp.N(pb[1]))
                    if abs(va - vb) <= 1e-3 * max(1.0, abs(vb)):
                        return {"verdict": "uncertain", "method": "sympy-approx",
                                "detail": "近似值（可能四舍五入）；请确认答案要求的保留位数"}
                except Exception:
                    pass
            return {"verdict": "different", "method": "sympy",
                    "detail": "化简后不相等"}
        except Exception as e:
            sympy_err = str(e)[:120]
    else:
        sympy_err = "未安装 sympy"

    # Math-Verify（LaTeX 友好）
    try:
        from math_verify import parse as mv_parse, verify as mv_verify
        if mv_verify(mv_parse(o), mv_parse(m)):
            return {"verdict": "same", "method": "math_verify", "detail": "Math-Verify 判定等价"}
    except Exception as e:
        mv_err = str(e)[:80]
    else:
        mv_err = ""

    num = _numeric_fallback(m, o)
    if num is True:
        return {"verdict": "same", "method": "numeric", "detail": "数值近似一致"}
    if num is False:
        return {"verdict": "different", "method": "numeric", "detail": "数值不同"}

    return {"verdict": "uncertain", "method": "none",
            "detail": f"无法解析（sympy: {sympy_err}"
                      + (f"; math_verify: {mv_err}" if mv_err else "") + "）"}


def solve_equation(eq_text, var="x"):
    if sp is None:
        raise SystemExit("求解需要 sympy：pip install sympy")
    t = preprocess(eq_text)
    if "=" in t:
        l, r = t.split("=", 1)
        eq = sp.Eq(to_expr(l), to_expr(r))
    else:
        eq = sp.Eq(to_expr(t), 0)
    x = sp.Symbol(var)
    sols = sp.solve(eq, x)
    return sols


def check_value(eq_text, value, var="x"):
    if sp is None:
        raise SystemExit("代入检验需要 sympy：pip install sympy")
    t = preprocess(eq_text)
    l, r = (t.split("=", 1) + [""])[:2] if "=" in t else (t, "0")
    x = sp.Symbol(var)
    v = to_expr(value)
    diff = sp.simplify(to_expr(l).subs(x, v) - to_expr(r).subs(x, v))
    ok = sp.simplify(diff) == 0
    return {"ok": bool(ok), "residual": str(diff)}


def main():
    ap = argparse.ArgumentParser(description="数学答案等价判定")
    ap.add_argument("--mine", help="我的/盲解答案")
    ap.add_argument("--official", help="文档/官方答案")
    ap.add_argument("--answers", help="批量：官方答案 JSON")
    ap.add_argument("--solver", help="批量：待核对答案 JSON")
    ap.add_argument("--equation", help="方程（用于 --value 代入检验或 --solve）")
    ap.add_argument("--value", help="方程的解（代入检验）")
    ap.add_argument("--solve", help="解方程，输出解集")
    ap.add_argument("--var", default="x", help="未知数（默认 x）")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--fail-on-different", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.solve:
        print(json.dumps({"equation": args.solve,
                          "solutions": [str(x) for x in solve_equation(args.solve, args.var)]},
                         ensure_ascii=False, indent=1))
        return 0
    if args.equation and args.value:
        res = check_value(args.equation, args.value, args.var)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res["ok"] else 1
    if args.mine and args.official:
        res = verify_answer(args.mine, args.official)
        res.update({"mine": args.mine, "official": args.official})
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if (res["verdict"] != "different" or not args.fail_on_different) else 1

    if not (args.answers and args.solver):
        sys.exit("请提供 --mine/--official，或 --answers/--solver，或 --self-test")

    official = json.load(open(args.answers, encoding="utf-8-sig"))
    solver = json.load(open(args.solver, encoding="utf-8-sig"))

    def as_map(d):
        if isinstance(d, dict):
            return {str(k): str(v) for k, v in d.items()}
        return {str(it.get("qid") or it.get("qno")): str(it.get("answer", "")) for it in d}

    off, sol = as_map(official), as_map(solver)
    items = []
    for k in sorted(set(off) & set(sol), key=lambda x: (len(x), x)):
        r = verify_answer(sol[k], off[k])
        r.update({"qid": k, "official": off[k], "mine": sol[k]})
        items.append(r)
    only_off = sorted(set(off) - set(sol))
    only_sol = sorted(set(sol) - set(off))
    summary = {
        "total": len(items),
        "same": sum(1 for x in items if x["verdict"] == "same"),
        "different": sum(1 for x in items if x["verdict"] == "different"),
        "uncertain": sum(1 for x in items if x["verdict"] == "uncertain"),
        "only_official": only_off, "only_solver": only_sol,
    }
    out = {"summary": summary, "items": items}
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        json.dump(out, open(os.path.join(args.out, "verify_results.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)
        md = ["# 数学答案等价判定", "",
              f"比对 {summary['total']} 题：等价 {summary['same']}，"
              f"不等价 {summary['different']}，无法解析 {summary['uncertain']}", "",
              "| 编号 | 文档答案 | 我的答案 | 判定 | 方法 |", "|---|---|---|---|---|"]
        for x in items:
            md.append(f"| {x['qid']} | {x['official']} | {x['mine']} | "
                      f"{x['verdict']} | {x['method']} |")
        open(os.path.join(args.out, "verify_report.md"), "w", encoding="utf-8").write(
            "\n".join(md) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if (summary["different"] and args.fail_on_different) else 0


def self_test():
    cases = [
        ("2√3", "√12", "same"), ("8/3", "2.6666666667", "same"),
        ("x=5或x=-1", "5，-1", "same"), ("{2,3}", "3、2", "same"),
        ("-2≤x≤3", "[-2,3]", "same"), ("(1,2)", "(1，2)", "same"),
        ("20%", "1/5", "same"), ("1又1/2", "3/2", "same"),
        ("x=5", "5", "same"), ("2x+1", "2x+2", "different"),
        ("5", "6", "different"), ("3/4", "0.75", "same"),
        ("5cm", "5", "same"), ("\\frac{1}{2}", "0.5", "same"),
        ("x>2", "(2,+∞)", "same"), ("x^2-5x+6=0", "x=2或x=3", "same"),
        ("1/3", "0.333", "uncertain"),
    ]
    bad = []
    for mine, off, expect in cases:
        r = verify_answer(mine, off)
        ok = r["verdict"] == expect
        print(f"[{'PASS' if ok else 'FAIL'}] {mine!r} vs {off!r} → {r['verdict']} "
              f"({r['method']})" + ("" if ok else f"，期望 {expect}"))
        if not ok:
            bad.append((mine, off, r))
    print(f"\n自检: {len(cases) - len(bad)}/{len(cases)} 通过")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
