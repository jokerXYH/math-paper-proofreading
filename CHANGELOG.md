# 更新记录

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## v2.3.0 — 2026-10-22

### 新增

- **答案数学等价引擎** `scripts/verify_answer.py`：SymPy + Math-Verify 双引擎，
  覆盖分数/根式/小数/百分数/带分数、解集、区间、不等式、坐标、方程解、多解顺序、中文单位；
  近似值（`1/3` vs `0.333`）判 `uncertain`，不武断判对。
- **盲解比对接入数学等价**：`compare_answers.py` 对 `2√3` vs `√12`、`x>2` vs `(2,+∞)` 等判"一致"。
- `requirements-math.txt`、`references/math-verification.md`（验证协议、工具选型、边界）。

### 变更（判定口径）

- **题目允许改编**：换数/换情境/换问法都不是错误；`diff_question.py` 的差异降级为
  `info/check` 线索，不再用"数字不一致=高优先"引导判错。
- `ai_review_tasks.md` 结论改为 `adapted_ok|local_logic_error|local_answer_error|uncertain`。
- 判定只看：题目逻辑/条件/图文是否自洽；答案是否数学正确且写全。
- 自检扩到 **40 项**（新增数学等价自检、盲解等价、改编语义）。

### 修复

- CI 在无 Pillow 环境把审阅台图片回退为 PNG，测试只认 JPEG 导致失败；改为接受任意内嵌图片格式。

## v2.2.0 — 2026-10-22

### 新增

- **多栏版面识别（1–4 栏）**：`scripts/recognition.py` 用栏缝检测 + XY-cut 还原阅读顺序；双栏/三栏试卷按栏切题/裁剪，
  左右栏不再串题、串图；`extract_pdf.py` 与 `cut_questions.py` 均已接入，`--no-columns` 可强制单栏。
- **扫描版 OCR 兜底**：`scripts/ocr_pdf.py` 自动选择 RapidOCR / PaddleOCR / Tesseract，
  输出逐行文本 + 低置信行清单 + 带隐形文本层的可检索 PDF，可直接接 `cut_questions.py`。
- **原题检索**：`scripts/search_original.py` 支持 bing / duckduckgo / 菁优网（Cookie）/ 离线链接，
  带 7 天缓存、1.2s 限速与 robots 检查，输出候选与可点清单。
- **逐字差异定位**：`scripts/diff_question.py` 归一化全角/数学符号后做字符级 diff，
  数字不一致最高优先，能识别"原题尾部含答案"避免误报；只出证据，不代替判定。
- **HTML 审阅台**：`scripts/make_review.py` 生成单文件交互页：题目列表/小图/识别文本/
  原题对照（差异高亮）/问题卡/整页定位/键盘切换/复核结果导出 JSON。
- **非题目条目标注**：知识清单/方法总结里的编号条目会标 `likely_question=false`，
  检索与盲解默认跳过，不再污染题号链。
- **全局 qid**：每题生成唯一 `Q001…`，多章节题号重复（如 1–20 后又从 1 开始）时，
  盲解答案、检索与差异结果不再互相覆盖。
- 自检从 21 项扩到 **40 项**：新增双栏/三栏切题、不串栏、差异分级、审阅台、离线检索、OCR 兜底、知识条目标注、qid 唯一性检查。

### 变更

- `extract_pdf.py` 文本按栏感知阅读顺序输出，report 增加"N 栏"与版面诊断。
- `align_answers.py` 题目端改用栏感知锚点，并跳过卷末答案区。
- `SKILL.md` 工作流加入 OCR、原题检索、差异定位、HTML 审阅台；红线补充"差异只是线索"。
- 新增 `references/recognition.md`（识别原理、OCR/版面/公式工具选型与许可提醒）。

## v2.1.0 — 2026-10-22

### 修复

- **答案区不再混入题目**：`cut_questions.py` 自动识别卷末「参考答案 / 答案与解析 / 解析」区，
  拆到 `answers.json` 与 `crops/a_pgXX_qYY.png`；此前答案行会被当成新题，造成题号重复、
  盲解任务书混入答案。
- **盲解任务题号去重**：`make_solver_tasks.py` 跳过重复/空白题目并提示，任务书不再出现重复题号。
- **答案分离对齐**：`align_answers.py` 在题目 PDF 一侧也跳过答案区；对非 PDF/TXT/MD 文件给出明确报错。

### 新增

- `scripts/prepare_input.py`：图片 / 图片文件夹 / DOCX → PDF 统一入口（DOCX 需本机 LibreOffice 或 Word）。
- `scripts/validate_skill.py`：技能结构、frontmatter、引用完整性、脚本 `--help`、依赖与仓库卫生自检。
- `tests/make_sample_pdf.py`：内置迷你样卷生成器（2 页 / 8 题 / 带答案区）。
- `requirements.txt`、`CHANGELOG.md`、版本元数据（frontmatter `metadata.version`）。
- 自检从「依赖私有样卷的 17 项」升级为「内置样卷 21 项 + 可选黄金样卷」：
  `python scripts/run_regression.py` 开箱即跑，`--pdf` 追加私有样卷回归。

### 变更

- `SKILL.md` 增加第 0 步环境与自检；补充答案区拆分说明；脚本清单加入 `validate_skill.py`。
- `README.md` 补充自检、常见问题与打包说明。

## v2.0.0 — 2026-10-16

- 题目 + 答案双模式校对；题目级切图、跨页合并、题号链诊断。
- 答案分离对齐、盲解交叉验证、错别字筛查。
- 红色批注写回 PDF（宽度/越界/遮挡三重检查）、markdown + 单文件 HTML 报告。

## v1.0.0 — 2026-10-16

- 首版：PDF 识别、答案核对、批注与报告基础流程。
