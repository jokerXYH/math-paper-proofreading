---
name: math-paper-proofreading
description: 校对初中/高中数学试卷的题目与答案（PDF/图片/DOCX，支持多栏版面与扫描版 OCR）。核心口径：题目允许改编，只查逻辑是否自洽/可解/图文一致；答案必须数学正确，用 SymPy + Math-Verify 做等价判定（分数/根式/解集/区间/方程解），再结合独立复算、程序验证与盲解交叉验证。产出红色批注版 PDF、单文件 HTML 审阅台（题目小图 + 原题线索 + 差异高亮 + 问题卡）和结论汇总表。当用户要求"检查题目""校对试卷""查错""核对答案""答案对不对""把错误圈出来/做批注"等数学试题检查场景时使用，尤其针对初高中数学、菁优网题源的试卷。
license: MIT
metadata:
  version: 2.3.1
  author: jokerXYH
  homepage: https://github.com/jokerXYH/math-paper-proofreading
---

# 初中数学试卷校对（题目 + 答案双模式）

## 核心原则（先读，防误报）

1. **"答案不唯一"本身不是题目错误。** 多解是规律探究、几何存在性、分类讨论等题型的正常设计（例如"所有值""可能是"类题目）。按下表判定：

| 判定 | 含义 | 输出 |
|---|---|---|
| 🔴 题目逻辑错误 | 条件矛盾、缺条件导致无解、图文不符、题号错乱影响作答 | 红框 + 修改建议 |
| 🔴 答案错误 | 答案数学上错误（需独立求解 + 程序/等价验证） | 红框 + 正确答案 |
| 🔴 答案不全 | 题目多解但答案只写了部分情况 | 红框 + 补全所有解 |
| 🟠 存疑 | 无法独立验证、OCR 低置信、近似值未确认 | 橙框 + 说明疑点 |
| 🔵 提示 | 多解已写全、表述可优化、易错提醒 | 蓝字备注 |
| ⚪ 改编 | 与网上原题不同，但本地题逻辑自洽、答案正确 | **不算错误**，仅记录 |

2. **一切结论要有依据**：独立复算（必做）＋ 程序化验证（能编程的题必做）＋ 原题/官方答案比对（能查到就查）。三项都完成后再写"错误"。
3. **可计算题优先写 Python 跑一遍**，不要只靠心算：枚举、模拟、周期检验最容易"看起来对"。
4. **题目允许改编**：换数、换情境、换问法都可以，**与原题不一致不是错误**。题目只看"逻辑是否自洽、是否可解、图文是否一致"。
5. **答案必须数学正确**：答案形式不同但等价（`2√3=√12`、`8/3≈2.667`、`x=5` 与 `5`）算正确；多解必须写全；近似值要确认保留位数。
6. 所有输出使用中文。

## 第0步：环境与自检（每次开工先跑，10 秒）

```bash
python -c "import pymupdf, sys; print('pymupdf', pymupdf.__version__, sys.version)"  # 唯一必需依赖
python scripts/validate_skill.py        # 结构/脚本/引用完整性自检
python scripts/run_regression.py        # 41 项全流程自检（内置单栏+双栏+三栏样卷，零外部依赖）
```

- 缺 pymupdf：`pip install pymupdf`（或 `pip install -r requirements.txt`）。
- **答案精确判定（强烈建议）**：`pip install -r requirements-math.txt`（SymPy + Math-Verify），然后
  `python scripts/verify_answer.py --self-test` 应 17/17 通过。
- 扫描版另装 OCR 引擎（推荐）：`pip install rapidocr-onnxruntime`；不装则只能人工看图。
- 自检不通过先修环境，**不要带着坏环境开始校对**。
- 有私有黄金样卷时：`python scripts/run_regression.py --pdf 原稿.pdf`（追加题数/跨页/错字命中检查）。
- 批量校准（多份真卷）：`python tools/batch_audit.py 试卷目录 -o 报告 --cut`，先看 `audit.md` 的疑似问题。

## 工作流

复制清单跟踪进度：

```
Task Progress:
- [ ] 0. 环境自检：validate_skill.py + run_regression.py（41 项全过）
- [ ] 1. 识别文档：prepare_input（图片/DOCX→PDF）→ OCR（扫描版）→ extract_pdf（文本+逐页图，栏感知）→ cut_questions（每题小图 + 答案区拆分）
- [ ] 2. 判断模式：看 answers.json / 搜"答案/解析/参考答案"；无答案＝模式A，含答案＝模式B（答案分离在另一文件？先 align_answers.py 配对）
- [ ] 3. 拆题建清单：题号、页码、栏、是否含答案、题型（cut_questions 输出）
- [ ] 4A. 模式A检查：题号系统 + 题干逐字（typo_scan 候选+回图复核）+ 图文一致 + 可解性
- [ ] 4B. 模式B验证：逐题手推 → 程序验证 → 盲解交叉验证 → 原题检索(search_original) → 差异定位(diff_question) → AI 判定
- [ ] 5. 分级汇总：🔴错误 / 🟠存疑 / 🔵提示 / ✅通过
- [ ] 6. 可视化：make_review（HTML 审阅台，先看这里）→ locate 定位 → draw_annotations 出批注版 PDF
- [ ] 7. 报告：make_report 出 markdown + 单文件 HTML 报告，预览给用户
```

### 第1步：识别文档

```bash
# 输入是图片 / 扫描件文件夹 / DOCX？先统一成 PDF（已是 PDF 则跳过）
python scripts/prepare_input.py 试卷.docx -o 输出/input
python scripts/prepare_input.py 扫描件目录/ -o 输出/input --name 试卷.pdf

# 扫描版（无文本层）：先 OCR，产出可检索 PDF + 低置信行清单
python scripts/ocr_pdf.py 试卷.pdf -o 输出/ocr          # 自动选 rapidocr/paddleocr/tesseract

python scripts/extract_pdf.py 试卷.pdf -o 输出目录 --dpi 160        # 全文+逐页图+题号诊断（栏感知）
python scripts/cut_questions.py 试卷.pdf -o 输出目录/cut --merge    # 题目级切图（逐题看图用这个）
```

- **cut_questions.py 是逐题核对的主力**：每题一张小图（跨页/跨栏题自动拼接为"合并"图），图形/表格绝不漏看；输出题号链诊断。
- **多栏试卷已按栏切分**：`questions.json` 的 `column` 字段标明第几栏（支持 1–4 栏），裁剪不会串栏；栏检测误判时加 `--no-columns`。
- **卷末"参考答案/解析"区会自动识别并拆到 `answers.json`**（答案小图 `crops/a_pgXX_qYY.png`），不再混进题目；若排版特殊被误拆，加 `--keep-answers` 回到旧行为，或直接按答案文件用 align_answers 处理。
- 文本层缺失（扫描版）会提示；OCR 的低置信行见 `ocr/lines.json` 的 `low_confidence`，**数字必须回图复核**。
- 局部放大用 `extract_pdf.py --crop 页码:x0,y0,x1,y1:备注`。

### 第2步：判断模式

- 搜全文关键词：`答案`、`参考答案`、`解析`、`【答案】`。
- 注意混合文档：题目中有个别答案、或答案在最后几页。
- 已用 `cut_questions.py` 时先看 `answers.json`：非空说明卷末有答案区，可直接作为官方答案来源。
- **答案卷（每题下方紧跟【答案】/【解答】）不会生成 `answers.json`**：`questions.json` 的 `text` 只保留题干（给检索/盲解用），`text_full` 保留完整解答；核对答案时看 `text_full` 与题目小图。
- **答案与题目分离在两个文件**（题目 PDF + 答案 PDF/TXT）时，先自动配对：

```bash
python scripts/align_answers.py 题目.pdf 答案.pdf -o align
# 输出 alignment.json（配对结果）+ report.txt（缺答案/多余答案清单，先处理这两类再核对）
```

### 第3步：拆题建清单

- 按 `^\d+．` 形态的题号行切分（脚本已自动做初切）；人工复核跨页题、嵌套小题（（1）（2）（3））。
- 重点关注**题号序列**，模式A/B都要查：
  - 连续编号中出现的重复、跳号、乱序；
  - 跨页衔接（如第11题在上一页、下一页直接跳到"7."这种）；
  - 题号与"题型/Part/章节"层级是否匹配。

### 第4A步：题目检查（模式A核心）

逐项目检（对照 references/error-checklist.md 完整清单）：

1. **题号系统**：全卷扫一遍编号序列，列出重复/跳号/错位清单。
2. **题干逐字**：
   - 错别字、漏字、多字（典型：漏"化"字、"正数"vs"正整数"这类限定词需结合答案确认意图）；
   - 标点误用（典型：数列逗号误打成加号：`a1+a2+…a99` 应为 `a1，a2，…，a99`）；
   - 箭头/条件词（"至多/至少/不超过/不小于"）、单位。
3. **图文一致**：把图放大逐项核对——图中数字、字母、箭头、阴影、刻度与文字描述是否一致（典型：题目说"框出8,10,16,22,24"，图上框的位置必须是这五个数）。
4. **可解性**：自己当学生把题做一遍。做不出/觉得条件不够时：
   - 是规律题设计如此（多解、开放）→ 🔵提示；
   - 明显缺条件/前后矛盾 → 🟠存疑（写明理由），严重矛盾→🔴。
5. **页结构**：整页空白、题目被截断、选项缺失/重复、图表与被引文字跨页过远。
6. **错别字筛查（高召回候选）**：`python scripts/typo_scan.py 试卷.pdf -o typo` —— 错字表/叠字/标点/括号配对/数列加号等规则扫描；再把 `typo/llm_review_prompt.md` 交给模型做语义通读（找漏字、病句类）。**所有候选必须回渲染图复核后才进报告**（"偶数数位""收获满满"这类是误报，已在白名单）。
7. 输出：`题号 → 问题类型 → 证据（原文截图/位置） → 修改建议`。

### 第4B步：答案核对（模式B核心）

1. **逐题独立复算（手推）**：不看文档答案，先做出自己的答案，再对照。
2. **程序化验证**（可编程题必做）：按 references/verification-recipes.md 选择模板——枚举、模拟、周期检测、公式验证等。scripts/verify_examples.py 里有可直接改用的真实案例。
3. **答案等价判定（必做，防止"形式不同被误判"）**：

```bash
# 两个答案是否数学等价（分数/根式/小数/解集/区间/多解顺序）
python scripts/verify_answer.py --mine "2√3" --official "√12"
# 方程解代入检验
python scripts/verify_answer.py --equation "2(x-1)=x+3" --value "5"
# 直接求解，和文档答案对照
python scripts/verify_answer.py --solve "x^2-5x+6=0"
```

- `same`（等价）/ `different`（不等价）/ `uncertain`（近似值或无法解析，列🟠存疑）。
- **答案必须过这一步**；不能只靠肉眼或字符串比对。`compare_answers.py` 已自动接入数学等价。
4. **盲解交叉验证（防自证偏差）**——重要题/不一致题必做：

```bash
python scripts/make_solver_tasks.py 输出/cut/questions.json -o solver_tasks
# 把 task_XX.md 交给 subagent / 另一个模型盲解（不给它官方答案！），收集为 solver_answers.json
python scripts/compare_answers.py --official 官方.json --solver solver_answers.json -o cmp
```

- 判定纪律：盲解与官方**不一致 → 列入🟠存疑**，人工第三遍复核后再下结论，**绝不因盲解不一致就直接判官方错**；
- **任务书/`solver_answers.json` 用全局 `qid`（Q001…）**，多章节题号重复也不会互相覆盖；原题号只用于对照；
- 多解答案顺序不同、B 与 B(2) 这类写法差异，比对器会自动识别为"一致"。

5. **原题检索 + 差异定位（只作参考，不要求题干一致）**：

```bash
# 生成检索（默认 360 + bing + offline；菁优网需 Cookie：JYEOO_COOKIE）
python scripts/search_original.py --questions 输出/cut/questions.json -o 输出/search --limit-q 10
# 本地识别 vs 原题：数字/运算符/文字差异（只出证据）
python scripts/diff_question.py --originals 输出/search/search_results.json -o 输出/diff
```

- `queries.md` 里有可点击链接；菁优网/学科网常需登录，**优先用浏览器打开人工核对**（或把 Cookie 配到环境变量）。
- `ai_review_tasks.md` 是给模型/子代理的判定任务书：逐题输出
  `{"qid","conclusion":"adapted_ok|local_logic_error|local_answer_error|uncertain","reason","confidence"}`。
- 差异分级：数字/运算符/条件变化 → **按本地题目重新计算**，不是错误；文字/标点差异 → 版本改编，忽略。
- **AI 判定纪律**：题目允许改编，**与原题不同 ≠ 错误**。先独立解本地题、用 `verify_answer.py` 验证答案；只有"本地逻辑错 / 本地答案错"才报错，其余记为改编或存疑。
- 原题也可能被题库二次编辑；原题答案只作参考，最终以本地题目重算为准。

6. **分类入表**：
   - 答案错误：给出"错在哪 + 正确答案 + 依据"；
   - 答案不全：列出完整解集（这属于答案问题！）；
   - 过程错误（答案对）：指出过程错处；
   - 题目问题：沿用模式A的判定。
7. 记录格式：`{题号, 我的独立答案, 文档答案, 是否一致, 验证方式（自算/程序/等价/盲解/原题）, 备注}`。

### 第5步：分级汇总

逐题记录后按判定分级，宁可存疑不可误报：

| 级别 | 使用条件 | 报告中颜色 |
|---|---|---|
| `error` | 题目真错 / 答案真错 / 答案不全（三项证据齐全） | 🔴 红 |
| `doubt` | 自算与原题矛盾且第三遍未定、OCR 低置信未复核 | 🟠 橙 |
| `hint` | 多解已写全、表述可优化、易错提醒 | 🔵 蓝 |
| `pass` | 已独立复算 + 程序/原题验证通过 | ✅ 绿 |

- 同一题既有题目问题又有答案问题 → 拆成两条 issue，不要合并描述。
- 记录格式：`{题号, 我的独立答案, 文档答案, 是否一致, 验证方式（自算/程序/盲解/原题）, 备注}`。

### 第6步：可视化（先审阅台，再批注 PDF）

**6.1 单文件 HTML 审阅台（推荐先看这个）**

```bash
python scripts/make_review.py \
  --questions 输出/cut/questions.json \
  --results 输出/results.json \
  --diff 输出/diff/diff_results.json \
  --verify 输出/verify/verify_results.json \
  --pages 输出/extract/pages \
  --pdf 试卷.pdf \
  -o 输出/审阅台.html
```

- 左侧题目列表（状态/相似度/搜索过滤），右侧：题目小图 + 识别文本 + 原题对照（数字差异高亮）+ 问题卡 + 来源链接；
- 「整页定位」在页面图上叠加题框，点击跳题；键盘 `j/k` 切题、`1/2/3/4` 标状态；
- 人工复核结果存 localStorage，可「导出复核 JSON」交回 AI；没有原题/差异时也能单独用。

**6.2 红色批注版 PDF**

**第一步用 locate.py 自动定位（不要再手填坐标）：**

```bash
python scripts/locate.py 试卷.pdf "变化而变" --page 3 --color red
# → 输出命中清单（带上下文行）+ 可直接粘贴的 marks JSON 片段；多个命中用上下文区分
```

**第二步写出批注版（自动做宽度/越界/遮挡三重检查）：**

写一个 JSON 规格文件后用脚本一次生成（红框 + 红字直接画进 PDF 内容层）：

```json
{
  "marks": [
    {"page": 6, "rect": [31, 43, 53, 64], "color": "red", "width": 1.6},
    {"page": 8, "rect": [163, 332, 316, 475], "color": "red", "width": 1.8}
  ],
  "notes": [
    {"page": 6, "x": 60, "y": 782, "size": 8.5, "color": "red",
     "lines": ["▲本题题号“7”有误：与前文第7题重复——应改为“12.”，后续题号顺延。"]},
    {"page": 5, "frame": [60, 380, 535, 432], "x": 72, "y": 402, "size": 10, "color": "red",
     "lines": ["▲本页整页空白，疑似排版遗留：请删除或补内容。"]}
  ]
}
```

```bash
python scripts/draw_annotations.py --src 试卷.pdf --spec spec.json --dst 试卷（红色批注版）.pdf --check-dir check/
# 自动渲染所有被标注页面为 PNG 供检查；脚本会警告超宽文字行
```

批注规范：
- 颜色：红=确定错误；橙=存疑；蓝=提示。批注文字格式：`▲第X题：错在哪——应为：……`。
- **单行文字 ≤55 个汉字（字号9~10）**，太长手动分行；脚本会给出宽度警告，被裁掉的批注等于没写。
- 位置优先放空白区（页边、题目下方），不要压在原文字上；有空白页时批注放页面中间。
- 输出物：`xxx（红色批注版）.pdf` + 标注 PNG + 汇总表，并预览给用户。

### 第7步：报告（必交付）

把结论写成 results.json（level: error/doubt/hint），一条命令出两种报告：

```bash
python scripts/make_report.py results.json -o 报告目录
# → 校对报告.md（贴聊天/存档） + 校对报告.html（单文件、题目小图 base64 内嵌，可直接发给出题老师）
```

- **level 纪律**：只有"题目真错 / 答案真错 / 答案不全"用 `error`（红）；多解、建议用 `hint`（蓝）；验证不了的用 `doubt`（橙）。
- HTML 报告打开即看：每题一张卡（第几页·题号 → 错在哪 → 正确答案 → 依据 → 题目小图）。

```markdown
results.json 字段：
{"title","source","mode","date",
 "issues":[{"level","page","qno","type","desc","correct","evidence","crop"}],
 "verified":["已核对无误的答案清单…"]}
```

## 速查与参考（一层引用）

- 工具脚本（scripts/）：`prepare_input.py` 图片/DOCX→PDF｜`ocr_pdf.py` 扫描版 OCR｜`extract_pdf.py` 识别｜`cut_questions.py` 栏感知切题 + 答案区拆分｜`align_answers.py` 答案分离对齐｜`search_original.py` 原题检索｜`diff_question.py` 原题差异定位｜`make_review.py` HTML 审阅台｜`locate.py` 批注定位｜`draw_annotations.py` 批注生成（含三重检查）｜`make_report.py` 报告(md+HTML)｜`make_solver_tasks.py` 盲解任务｜`compare_answers.py` 盲解比对（含数学等价）｜`verify_answer.py` 答案等价判定｜`typo_scan.py` 错别字筛查｜`verify_examples.py` 验证模板｜`run_regression.py` 回归测试（41 项）｜`validate_skill.py` 结构自检｜`recognition.py` 栏检测/阅读顺序库
- 题目/答案错误完整清单与初中各模块易错点：[references/error-checklist.md](references/error-checklist.md)
- 各题型核验配方（含可直接改的代码模板）：[references/verification-recipes.md](references/verification-recipes.md)
- 识别精度、OCR、版面与公式工具选型：[references/recognition.md](references/recognition.md)
- 答案等价、求解与初高中数学验证协议：[references/math-verification.md](references/math-verification.md)
- PDF 识别/OCR/公式识别工具与 GitHub 项目（可按需克隆到 `references/github/`）：[references/toolchain.md](references/toolchain.md)
- 菁优网题源检索与比对流程：[references/jyeoo-workflow.md](references/jyeoo-workflow.md)

## 红线要求（最容易踩的坑）

1. **改编≠错误**：题目可以换数/换情境/换问法，与网上原题不同不报错；题目只看逻辑自洽、可解、图文一致。**多解≠错误**：多解题只给🔵提示（蓝），只有题目逻辑真错、答案真错、答案不全才🔴报错（红）。
2. 批注小字超宽会被整体裁掉——生成后**必须看渲染图**确认（脚本会警告宽度/越界/遮挡，警告不为空就修正重跑）。
3. 视觉识别的数字要复核（0/6、1/7、3/8、9/7），拿不准就放大再看。
4. 原题官方答案也可能多值（"23或32"很常见），这也印证"多解正常"；与自算矛盾时做第三遍验算再下结论。
5. 扫描版必须先 OCR，且 OCR 的数字每道题人工瞄一眼再把关。
6. **改完任何脚本，先跑 `python scripts/run_regression.py`**（内置单栏+双栏+三栏样卷 41 项，零外部依赖），全过再交付；有私有样卷时再加 `--pdf` 跑黄金回归。
7. **原题检索与差异只是"参考"**：`diff_question.py` 的数字/条件差异必须**按本地题重算**，不能直接判错；题目改编是允许的。
8. **答案必须过数学等价判定**：`verify_answer.py` / `compare_answers.py`；`same` 才算对，`uncertain`（近似值/无法解析）列🟠存疑，不能凭"看起来一样"。
9. **多栏卷必须检查 `column` 与裁剪图**：栏检测误判会导致题文/配图串栏，发现串栏立即 `--no-columns` 或人工设栏后重切。
10. `typo_scan.py` 与 `compare_answers.py` 的输出都只是**候选**：错字候选回图复核；盲解不一致一律先列🟠存疑复核，绝不直接判官方错。
