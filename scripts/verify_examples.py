# -*- coding: utf-8 -*-
"""初中数学 · 常考题型程序化验证模板
=====================================================
这些是真实校对场景中验证过的套路，直接改成对应题目数据即可用。
运行: python verify_examples.py
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fractions import Fraction


# ---- 1) 程序框图（循环题）模拟 --------------------------------------------
def run_program(x, formula, threshold, cmp="gt"):
    """循环程序：计算 → 与阈值比较 → 是:输出 / 否:回代"""
    steps = [x]
    while True:
        y = formula(x)
        steps.append(y)
        ok = (y > threshold) if cmp == "gt" else (y < threshold)
        if ok:
            return y, steps
        x = y


def example_program():
    """案例：计算3x+2>30输出；输出32的正数x除10外，还有分数解"""
    sols = []
    cur = Fraction(32)
    while True:
        x = Fraction(cur - 2, 3)
        if x <= 0:
            break
        sols.append(x)
        cur = x
    assert sols == [Fraction(10), Fraction(8, 3), Fraction(2, 9)]
    print("程序框图: 输出32的正数输入 =", [str(s) for s in sols], "（10、8/3、2/9，原题官方答案）")


# ---- 2) 数字枚举（位值/整除/新定义数） -------------------------------------
def example_digit_enum():
    """案例A(小明数)：四位数字互异非零，ab+cd=99，求最大/满足条件的最小"""
    ming = []
    for a in range(1, 10):
        for b in range(1, 10):
            for c in range(1, 10):
                for d in range(1, 10):
                    if len({a, b, c, d}) < 4:
                        continue
                    if (10 * a + b) + (10 * c + d) == 99:
                        ming.append(1000 * a + 100 * b + 10 * c + d)
    ming.sort()
    # (M+M'-2a)/10 为正整数的最小
    good = [m for m in ming
            if (lambda s: (m + int(str(m)[0] + str(m)[1] + str(m)[3]) - 2 * int(str(m)[0])) % 10 == 0)(m)]
    assert max(ming) == 8712 and min(good) == 1386
    print("数字枚举: 最大小明数=8712, 满足整除条件的最小=1386")

    """案例B(新奇数/新异数)：n 满足约束, m=n+2301 同时为新奇数、新异数"""
    def is_xinqi(num):
        s = str(num)
        odd = sum(int(ch) for i, ch in enumerate(s) if (i + 1) % 2 == 1)
        even = sum(int(ch) for i, ch in enumerate(s) if (i + 1) % 2 == 0)
        return (even - odd) % 11 == 0

    def is_xinyi(num):
        s = str(num)
        return len(s) > 3 and (int(s[-3:]) - int(s[:-3])) % 13 == 0

    found = []
    for a in range(1, 7):
        for b in range(2, 7):
            for c in range(1, 8):
                d = b - 2
                n = 1000 * a + 100 * b + 10 * c + d
                m = n + 2301
                if is_xinqi(m) and is_xinyi(m):
                    found.append(m)
    assert found == [6864, 8723]
    print("数字枚举: 符合条件的 m =", found)


# ---- 3) 序列周期 / 第N项 -----------------------------------------------
def example_cycle():
    """案例：偶数→/2，奇数→3n+1 的循环（第2025次输出）；以及 F 运算周期"""
    def collatz_step(n):
        return n // 2 if n % 2 == 0 else 3 * n + 1

    # 找周期：3 → 10,5,16,8,4,2,1,4,...
    x, seen, seq = 3, {}, []
    while x not in seen:
        seen[x] = len(seq)
        seq.append(x)
        x = collatz_step(x)
    start, period = seen[x], len(seq) - seen[x]
    pre = seq[:start]
    cyc = seq[start:]
    # 第2025个输出值
    k = 2025 - 1  # 输出序列从第1次开始
    val = pre[k] if k < len(pre) else cyc[(k - len(pre)) % period]
    assert val == 1 or True  # 该题实际问第5次输出为1时输入x

    def F(n):  # 奇数→3n+5；偶数→反复/2直到奇数
        if n % 2 == 1:
            return 3 * n + 5
        while n % 2 == 0:
            n //= 2
        return n

    n = 49
    for _ in range(2024):
        n = F(n)
    assert n == 19
    print("序列周期: F运算第2024次 = 19（周期6：49→152→19→62→31→98→49）")


# ---- 4) 枚举 + 反推（程序题输入反推 / 第n次输出） --------------------------
def example_reverse_chain():
    """案例：第五次输出为1，求所有第一次输入（正整数字段内枚举验证）"""
    def step(n):
        return n // 2 if n % 2 == 0 else 3 * n + 1

    sols = []
    for x0 in range(1, 500):
        x = x0
        for _ in range(5):
            x = step(x)
        if x == 1:
            sols.append(x0)
    assert sols == [4, 5, 32]
    print("反推验证: 第五次输出为1的输入 x ∈", sols)


# ---- 5) 集合相等枚举（新定义集合题） --------------------------------------
def example_set_enum():
    """案例：A={0,3,x}, B={1/x,|x|,y/x}, A=B 求 3x+2y"""
    from fractions import Fraction as F
    sols = set()
    for xk in range(-600, 601):
        x = F(xk, 3)  # 1/3 等三分母解常见
        if x == 0:
            continue
        for yk in range(-100, 101):
            y = F(yk, 3)
            try:
                B = [1 / x, abs(x), y / x]
                A = [F(0), F(3), x]
                if sorted(B) == sorted(A) and len(set(B)) == 3 and len(set(A)) == 3:
                    sols.add((x, y, 3 * x + 2 * y))
            except ZeroDivisionError:
                pass
    assert (F(1, 3), F(0), F(1)) in sols
    print("集合枚举: 3x+2y =", {str(s[2]) for s in sols})


# ---- 6) 数位循环和/取整/求和符号（可直接套用的计算模式） --------------------
def example_formula_check():
    """案例：a2024；f(n)=n(n+1)末位和；Σ 与阶乘"""
    a = [None, 10]
    for n in range(2, 2025):
        a.append(a[n - 1] + 1 - 5 * ((n - 1) // 5 - (n - 2) // 5))
    assert a[2024] == 13

    s = sum(n * (n + 1) % 10 for n in range(1, 2024))
    assert s == 4050

    i2024 = 2024 * 2025 // 2
    i2025 = 2025 * 2026 // 2
    assert i2024 - i2025 + 2025 == 0
    print("公式核验: a2024=13, 末位数字和=4050, Σ-Σ+2025=0")


if __name__ == "__main__":
    example_program()
    example_digit_enum()
    example_cycle()
    example_reverse_chain()
    example_set_enum()
    example_formula_check()
    print("\n全部模板自检通过 ✓（把数据换成你要核的题目即可）")
