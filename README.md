# 数学试卷校对 Skill（math-paper-proofreading）v2.3

> 面向**初中/高中数学**试卷的「题目 + 答案」双模式校对 Agent Skill：
> 识别 PDF → 逐题核对 → 答案数学等价验证 → 原题线索/差异 → 红蓝批注 → 单文件 HTML 审阅台。
> **题目允许改编，只查逻辑；答案必须数学正确。** 支持双栏/三栏、扫描版 OCR，开箱自带 40 项自检。

[![version](https://img.shields.io/badge/version-2.3.0-blue)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 它能做什么

| 能力 | 说明 |
|---|---|
| 🔍 **模式A（纯题目）** | 检查逻辑自洽、条件是否充分、可解性、图文一致性、题号链、页结构；**题目允许改编，不要求与原题一致** |
| ✅ **模式B（含答案）** | 逐题独立复算 + Python 程序验证 + **答案数学等价判定** + 盲解交叉验证 + 原题线索，判定：答案错误 / 答案不全 / 过程错误 / 存疑 |
| 🧮 **答案等价判定** | `verify_answer.py`：分数/根式/小数/解集/区间/多解/方程解，SymPy + Math-Verify 双引擎；形式不同但等价不再误判 |
| 🧩 **多栏版面感知（1–4 栏）** | XY-cut 还原阅读顺序，按栏切题与裁剪，左右栏不串题、不串图 |
| 🖼️ **扫描版 OCR** | RapidOCR / PaddleOCR / Tesseract 自动选择，输出低置信行清单 + 可检索 PDF |
| 🧩 **答案区自动拆分** | 卷末「参考答案/解析」自动识别进 `answers.json`，不再被当成新题；题目与答案分两个文件时用 `align_answers.py` 按题号配对 |
| 🔤 **错别字自动筛查** | 规则引擎高召回（错字表/叠字/标点/括号配对/数列加号）+ 生成 LLM 通读提示词（语义漏字交给模型） |
| 🔎 **原题线索（非标准答案）** | `search_original.py` 检索候选；`diff_question.py` 标版本差异；**改编≠错误**，按本地题重算 |
| 🖍️ **可视化批注** | 红框 + 红字**直接写进 PDF 内容层**（任何阅读器/打印可见）：错在哪、正确答案是什么 |
| 🖥️ **HTML 审阅台** | 单文件交互页：题目列表 + 小图 + 识别文本 + 原题对照（差异高亮）+ 问题卡 + 整页定位；复核结果可导出 JSON |
| 📊 **报告** | 单文件 HTML 报告：每题一张卡（题目小图 + 错因 + 正确答案 + 依据），可直接发人 |
| 📏 **判定纪律** | 改编/多解 ≠ 错误；只有**题目逻辑错、答案错、答案不全**才标🔴（红） |
| 🧪 **可回归** | 内置单栏 + 双栏 + 三栏样卷，clone 下来一行命令跑完 40 项自检 |

## 工作流

```
PDF/图片/DOCX ──prepare/OCR──► 可检索 PDF
      │
      ▼
extract/cut ──► 每题小图 + 文本 + 题号链 + answers.json（双栏按栏）
                         │（答案在另一个文件？align_answers 先配对）
              ┌──────────┴──────────┐
        模式A(纯题目)            模式B(带答案)
        逻辑/条件/图文/可解性      + 手推 + 程序验证 + 答案等价(verify_answer)
        + typo_scan 错别字候选         + 盲解交叉验证 + 原题线索(非标准)
              └──────────┬──────────┘
                          ▼
        分级汇总(🔴错误/🟠存疑/🔵提示/⚪改编) ──► make_review（HTML 审阅台）
                          ▼
              locate 定位 ──► 批注 PDF ──► make_report
```

## 安装

**方式一：git clone（推荐，便于更新）**

```bash
git clone https://github.com/jokerXYH/math-paper-proofreading.git
```

把整个文件夹放进 skills 目录：

- Windows：`C:\Users\<你的用户名>\.cursor\skills\`
- macOS / Linux：`~/.cursor/skills/`

**方式二：下载 ZIP** —— 解压后把 `math-paper-proofreading` 文件夹放进上面的 skills 目录。

安装依赖（唯一必需项）：

```bash
pip install -r requirements.txt        # 必需：pymupdf
pip install -r requirements-math.txt   # 强烈建议：sympy + math-verify（答案等价）
```

> 扫描版另装 OCR 引擎（推荐 RapidOCR，约 80MB）：`pip install rapidocr-onnxruntime`
>
> OCR（扫描版试卷）、公式识别、整页转 Markdown 的可选工具链见 `references/toolchain.md` 与 `references/recognition.md`。

## 30 秒验证安装

```bash
cd math-paper-proofreading
python scripts/validate_skill.py    # 结构 / 引用 / 脚本可用性
python scripts/run_regression.py    # 40 项全流程自检（内置单栏+双栏+三栏样卷，无需准备试卷）
python scripts/verify_answer.py --self-test   # 数学等价引擎 17 项
```

全部 PASS 即可开工；改完任何脚本后也跑这两条。

## 快速开始

```bash
# 0) 输入是图片 / 扫描件文件夹 / DOCX？先统一成 PDF
python scripts/prepare_input.py 试卷.docx -o 输出/input
python scripts/prepare_input.py 扫描件目录/ -o 输出/input --name 试卷.pdf

# 0.5) 扫描版先 OCR（自动选引擎；产出低置信行清单 + 可检索 PDF）
python scripts/ocr_pdf.py 输出/input/试卷.pdf -o 输出/ocr

# 1) 识别：全文 + 逐页图 + 题号链诊断（多栏自动按栏排序）
python scripts/extract_pdf.py 试卷.pdf -o 输出 --dpi 160

# 2) 题目级切图 + 卷末答案区自动拆分（逐题核对主力；跨页题自动拼接）
python scripts/cut_questions.py 试卷.pdf -o 输出/cut --merge
#    → questions.json / answers.json / crops/q_*.png / crops/a_*.png

# 3) 答案在另一个文件？先自动配对
python scripts/align_answers.py 试卷.pdf 答案.pdf -o 输出/align

# 4) 错别字筛查（候选需回图复核）；llm_review_prompt.md 交给模型做语义通读
python scripts/typo_scan.py 试卷.pdf -o 输出/typo

# 5) 盲解交叉验证：生成任务书 → subagent/另一个模型盲解 → 比对
python scripts/make_solver_tasks.py 输出/cut/questions.json -o 输出/tasks
python scripts/compare_answers.py --official 官方.json --solver solver_answers.json -o 输出/cmp

# 5.5) 答案数学等价（分数/根式/解集/区间；形式不同也能判对）
python scripts/verify_answer.py --mine "2√3" --official "√12"
python scripts/verify_answer.py --equation "2(x-1)=x+3" --value "5"

# 5.6) 原题线索（题目允许改编，差异≠错误；菁优网需 JYEOO_COOKIE）
python scripts/search_original.py --questions 输出/cut/questions.json -o 输出/search --limit-q 10
python scripts/diff_question.py --originals 输出/search/search_results.json -o 输出/diff

# 6) HTML 审阅台（先在这里看哪里有问题；可导出复核 JSON）
python scripts/make_review.py --questions 输出/cut/questions.json \
  --results 输出/results.json --diff 输出/diff/diff_results.json \
  --verify 输出/verify/verify_results.json \
  --pages 输出/extract/pages --pdf 试卷.pdf -o 输出/审阅台.html

# 7) 批注定位（关键词→坐标，免手填）
python scripts/locate.py 试卷.pdf "变化而变" --page 3 --color red

# 8) 生成批注版 PDF（自动做宽度/越界/遮挡三重检查）
python scripts/draw_annotations.py --src 试卷.pdf --spec spec.json --dst 批注版.pdf --check-dir check

# 9) 生成报告（markdown + 单文件 HTML）
python scripts/make_report.py results.json -o 报告目录

# 10) 有私有样卷时跑黄金回归（可选）
python scripts/run_regression.py --pdf 一份测试卷.pdf
```

## 脚本一览

| 脚本 | 作用 |
|---|---|
| `prepare_input.py` | **输入统一**：图片 / 图片文件夹 / DOCX → PDF（A4 等比居中） |
| `ocr_pdf.py` | **扫描版 OCR**：RapidOCR/PaddleOCR/Tesseract 自动选；低置信行 + 可检索 PDF |
| `extract_pdf.py` | 文本层提取（栏感知阅读顺序）+ 逐页渲染 + 题号链诊断 + 区域裁剪 |
| `cut_questions.py` | **题目级自动切图**：多栏按栏切、题号锚定、跨页/跨栏合并；卷末答案区自动拆分 |
| `align_answers.py` | **答案分离对齐**：题目 PDF + 答案 PDF/TXT 按题号自动配对，暴露缺答案/多余答案 |
| `search_original.py` | **原题检索**：bing / duckduckgo / 菁优网（Cookie）/ 离线链接，带缓存限速 |
| `diff_question.py` | **差异定位**：归一化后逐字 diff，数字不一致最高优先，输出证据不判对错 |
| `make_review.py` | **HTML 审阅台**：列表 + 小图 + 原题对照 + 差异高亮 + 整页定位 + 导出复核 JSON |
| `locate.py` | **批注定位助手**：关键词 → 坐标 → spec JSON 片段 |
| `draw_annotations.py` | 批注引擎：画入 PDF 内容层；宽度/越界/遮挡三重检查 |
| `make_report.py` | 报告生成：markdown + 单文件 HTML（图片内嵌） |
| `make_solver_tasks.py` | **盲解任务生成**：把题目打包成盲解任务书（自动去重） |
| `compare_answers.py` | **盲解比对**：与官方答案交叉验证，不一致自动列"存疑"；已接数学等价 |
| `verify_answer.py` | **答案等价判定**：SymPy + Math-Verify；分数/根式/解集/区间/方程解/近似值 |
| `typo_scan.py` | **错别字筛查**：规则高召回 + LLM 通读提示词 |
| `verify_examples.py` | 6 类常考题的程序化验证模板（程序框图/数位整除/周期/集合/公式…） |
| `recognition.py` | 版面库：栏检测、XY-cut 阅读顺序、题号锚定（供其它脚本调用） |
| `run_regression.py` | 40 项自检（内置单栏+双栏+三栏样卷；`--pdf` 追加黄金样卷回归） |
| `validate_skill.py` | 技能结构 / frontmatter / 引用 / 脚本 `--help` / 仓库卫生自检 |
| `tools/batch_audit.py` | **批量体检**：一次跑多份 PDF，输出多栏页/题号/0 号误判/回退/扫描件提示 |

## 批量体检（校准时用）

```bash
python tools/batch_audit.py 试卷样本/ -o 试卷样本/report --cut
```

一次跑多份 PDF，输出 `audit.md`（按疑似问题排序）与 `audit.json`：多栏页数、题号数、0 号误判、回退、扫描件提示。改栏检测/题号规则后先跑它，再抽看 `crops/`。

## 判定标准（关键）

| 判定 | 含义 |
|---|---|
| 🔴 题目逻辑错误 | 条件矛盾、缺条件无解、图文不符、题号错乱影响作答（**不是**"与原题不同"） |
| 🔴 答案错误 | 答案数学上错误（独立求解 + `verify_answer.py` 判定不等价） |
| 🔴 答案不全 | 题目多解但答案只写了部分情况 |
| 🟠 存疑 | 无法独立验证、OCR 低置信、近似值未确认，待人工复核 |
| 🔵 提示 | **多解/答案不唯一（答案写全即为正确）**、表述可优化、易错提醒——**不算错误** |
| ⚪ 改编 | 与网上原题不同但本地题逻辑自洽、答案正确——**不算错误** |

## 常见问题

**Q：卷末答案区没有被拆出来（或误拆了题目）？**
A：默认按「参考答案 / 答案与解析 / 解析 / 详解」这类独占一行的短标题识别。排版特殊时：
用 `--keep-answers` 回到旧行为；或把答案单独导出为 PDF/TXT，用 `align_answers.py` 配对。
拆分结果务必看一眼 `answers.json`，答案本身以数字开头时（如 `5．5`）可能被并到相邻条目。

**Q：扫描版 PDF 没有文本层？**
A：先按 `references/toolchain.md` 做 OCR，再跑本流程；OCR 出来的数字必须逐题看图复核。

**Q：批注文字被裁掉/压住原文？**
A：脚本会打印宽度/越界/遮挡警告；有警告就调整 `spec.json` 的行长（单行 ≤55 汉字）或坐标，重跑直到无警告，并打开 `check/` 下的检查图确认。

**Q：盲解结果和官方答案不一致，能直接判错吗？**
A：不能。先列🟠存疑，人工第三遍复核；多解顺序不同、`B` 与 `B(2)` 这类写法差异比对器会判为一致。

**Q：双栏试卷切出来的题串到另一栏了？**
A：先看 `report.txt` 是否检出"双栏"。误判时用 `cut_questions.py --no-columns` 强制单栏；确认是双栏但漏检，把该页截图反馈，调 `recognition.py` 的栏缝阈值。

**Q：菁优网检索不到 / 提示登录？**
A：菁优网站内搜索需要登录，且结果由 JS 渲染。优先把 `queries.md` 里的链接用浏览器打开人工核对，或设置 `JYEOO_COOKIE` 后重试；脚本不做高频抓取。

**Q：扫描版装哪个 OCR？**
A：优先 `pip install rapidocr-onnxruntime`（Apache-2.0、CPU 快、约 80MB）。追精度可换 PaddleOCR；只要轻量可用 Tesseract。OCR 的低置信行会标在 `lines.json`，数字必须回图复核。

**Q：答案卷是 3 栏/多栏，能自动处理吗？**
A：支持 1–4 栏自动检测（真卷答案册常见 3 栏），切图按栏裁剪、不串栏。超过 4 栏或栏缝被图形堵死时，脚本会告警；可用 `--no-columns` 强制单栏后人工核对。

**Q：一卷里题号重复（每章节都从 1 开始）怎么办？**
A：每题都有全局唯一 `qid`（Q001…）。盲解任务书、`solver_answers.json`、检索与差异结果都用 `qid` 关联，题号只用于显示，不会互相覆盖。

**Q：拍照/手写试卷能自动校对吗？**
A：不能可靠自动校对。手写体 OCR 置信度通常很低，脚本会明确告警"疑似手写/拍照"；请人工转录题干，或提供清晰扫描件/原始 PDF。

**Q：原题检索用哪个源？**
A：默认 360 + Bing + 离线链接（国内教育站收录更好）；菁优网需登录 Cookie。检索结果只是线索，`diff_question.py` 只标差异，最终由 AI/人结合渲染图与答案判定。

**Q：本地题目和原题不一样，要改吗？**
A：不用。题目允许改编（换数/换情境/换问法）。只要本地题逻辑自洽、可解、答案正确，就记为 ⚪改编，不算错误；只有条件矛盾/缺条件/图文不符/答案错才报错。

**Q：答案写成 0.333 或 2.67，算对吗？**
A：`verify_answer.py` 对 `1/3` vs `0.333` 判 `uncertain`（近似值），提示确认题目要求的保留位数；不武断判对或判错。分数/根式等价（`2√3=√12`）会判 `same`。

**Q：几何证明能自动判吗？**
A：不能自动判"证明过程是否严谨"。可计算部分（坐标、长度、角度、面积）用 SymPy/程序验证；证明结构按 `references/math-verification.md` 的清单人工/AI 复核。

**Q：HTML 审阅台太大 / 打不开？**
A：题目小图默认缩到 1000px JPEG 内嵌；页数特别多时去掉 `--pages`，或加 `--no-images` 只留文本，仍可配合 PDF 使用。

## 打包发布

```bash
# 生成可分发 zip（排除 .git / 运行产物 / 第三方克隆）
git archive --format=zip -o math-paper-proofreading-v2.3.0.zip HEAD
```

发布前必跑：`python scripts/validate_skill.py && python scripts/run_regression.py`。

## 参考与致谢

同类/相关开源项目（收录于 `references/toolchain.md`）：

- [ExamSplit AI](https://github.com/yizhaofeng1/pdf_processor) —— PyMuPDF 试卷切题工作台（本地规则 + 视觉兜底）
- [PaperCutter-VL](https://github.com/DovikN-913/PaperCutter-VL) —— 基于 PaddleOCR-VL 的试卷切题
- [MinerU](https://github.com/opendatalab/MinerU) / [marker](https://github.com/VikParuchuri/marker) —— PDF → Markdown
- [LaTeX-OCR (pix2tex)](https://github.com/lukas-blecher/LaTeX-OCR) —— 公式截图 → LaTeX
- [Math-Verify](https://github.com/huggingface/Math-Verify) —— 数学答案等价判定
- [pycorrector](https://github.com/shibing624/pycorrector) —— 中文文本纠错
- 菁优网工具：jyeoo-paper-formatter / Jyeoo-Userscripts / web-crawler

## 免责声明

- 本工具仅用于**教学教研场景下的试卷校对辅助**，校对结论仍需人工复核；
- 仓库不包含任何版权教材原文，请确保你对被校对材料拥有合法使用权；
- 爬虫类参考工具请遵守目标网站的服务条款。

## License

[MIT](LICENSE)
