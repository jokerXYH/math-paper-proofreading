# 数学能力：答案等价、求解与验证

> 目标：让"答案对不对"不靠肉眼看字符串，而是**数学等价判定 + 独立求解 + 代入检验**。
> 覆盖初高中代数/方程/不等式/根式/解集/坐标等高频题型；几何证明靠推理模板 + 坐标/枚举，不假装全自动。

---

## 一、为什么不用"和原题一样"当标准

试卷允许**改编**：换数、换情境、换问法、换设问顺序都正常。因此：

| 对象 | 判定标准 |
|---|---|
| 题目 | 逻辑自洽、条件充分、可解、图文一致；**与原题不同 ≠ 错误** |
| 答案 | 数学上正确、多解写全、形式可不同但等价 |
| 原题 | 只作参考答案/命题意图的线索，不是唯一真值 |

`diff_question.py` 只列"版本差异"，不判错；`ai_review_tasks.md` 要求按**本地题**重算。

## 二、工具选型

| 工具 | 许可 | 作用 | 取舍 |
|---|---|---|---|
| **SymPy** | BSD | 符号化简、解方程/不等式、集合/区间、代入检验 | **默认核心**，离线、可解释 |
| **Math-Verify**（HuggingFace） | MIT/Apache（以仓库为准） | LaTeX/数学答案抽取与等价判定（ANTLR + SymPy） | 处理 `\frac`、复杂 LaTeX 更稳 |
| latex2sympy2_extended | MIT | LaTeX → SymPy | Math-Verify 依赖 |
| sympy-mcp | 开源 MCP | 给 LLM 暴露 SymPy 能力 | 适合本地 MCP，不塞进技能默认依赖 |
| Lean / 形式化证明 | Apache | 严格证明 | 初高中成本过高，不默认 |
| GeoGebra / Desmos | 商业/免费 | 动态几何、函数图像 | 人工辅助，不做自动判题 |

安装：

```bash
pip install -r requirements-math.txt    # sympy + math-verify
python scripts/verify_answer.py --self-test
```

## 三、`verify_answer.py` 能判什么

```bash
python scripts/verify_answer.py --mine "2√3" --official "√12"
python scripts/verify_answer.py --mine "x=5或x=-1" --official "5，-1"
python scripts/verify_answer.py --mine "x>2" --official "(2,+∞)"
python scripts/verify_answer.py --equation "2(x-1)=x+3" --value "5"
python scripts/verify_answer.py --solve "x^2-5x+6=0"
python scripts/verify_answer.py --official official.json --mine mine.json -o 输出目录
```

支持：

- 整数/分数/小数/百分数/带分数（`1又1/2`）；
- 根式与幂（`√12`、`2√3`、`x²`、`^`）；
- 多解与解集（`x=2或x=3`、`{2,3}`、`2、3`）；
- 区间与不等式（`-2≤x≤3`、`[−2,3]`、`x>2`、`(2,+∞)`）；
- 坐标/数组（`(1,2)`）；
- 方程/方程解（`2x+1=5` vs `x=2`，解方程后比较）；
- 中文单位（`5cm` vs `5`，仅去尾部单位）；
- 近似值（`1/3` vs `0.333`）→ `uncertain`，提示确认保留位数，不武断判对。

结论：

| verdict | 含义 | 处理 |
|---|---|---|
| `same` | 数学等价 | 通过 |
| `different` | 不等价 | 列🔴答案错误（需再人工复核一次） |
| `uncertain` | 近似值/无法解析 | 列🟠存疑，人工或公式 OCR 后重判 |

## 四、初高中数学的验证协议（必须叠加，不可只靠工具）

1. **定义域/值域**：分式分母≠0、偶次根号≥0、对数真数>0、实际问题范围（人数/长度为正）。
2. **多解与分类**：绝对值、平方根、二次方程、几何存在性、动点问题，必须列全并检验取舍条件。
3. **代入检验**：方程/不等式解代回原式；几何坐标解代回距离/斜率/面积公式。
4. **特殊值/边界**：端点、0、1、负数、相等情形；不等式注意开闭区间。
5. **单位与精度**：题目要求保留几位、是否带单位；近似值不能当精确值。
6. **程序枚举**：整数解、数位、周期、组合计数用 Python 枚举交叉验证，禁止只靠心算。
7. **盲解**：重要题交给另一个模型独立做，再用 `compare_answers.py`（已接数学等价）比对。

## 五、已知边界

- **几何证明**：无法自动判定"证明过程"是否严谨；用坐标法/向量法把可计算部分程序化，其余按推理清单人工复核。
- **含参讨论**：SymPy 能解很多，但分类讨论的完整性仍需人工检查。
- **分段函数/带定义域限制**：解析器可能只比较表达式，需结合题目范围另判。
- **LaTeX 复杂公式/公式图**：先公式 OCR（pix2tex/PP-FormulaNet），再交给 `verify_answer.py`；OCR 错会直接导致误判。
- **手写答案**：不自动识别，必须人工转录。
- **近似值**：`0.333` vs `1/3` 判 `uncertain`，由人确认是否允许近似。

## 六、参考链接

- Math-Verify：https://github.com/huggingface/Math-Verify
- SymPy：https://www.sympy.org/
- latex2sympy2_extended：https://github.com/OrangeX4/latex2sympy
- sympy-mcp：https://github.com/sdiehl/sympy-mcp
- 数学验证研究（MathQ-Verify）：https://huggingface.co/papers/2505.13903
