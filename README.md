# 数学试卷校对 Skill（math-paper-proofreading）

> 面向**初中数学**试卷的「题目 + 答案」双模式校对 Agent Skill：
> 识别 PDF → 逐题核对 → 红蓝批注写回 PDF → 生成可视化报告。
> 主打**菁优网题源试卷**的教研校对场景。

## 它能做什么

| 能力 | 说明 |
|---|---|
| 🔍 **模式A（纯题目）** | 检查题干文字（错字/漏字/标点）、题号链（重复/跳号/乱序）、图文一致性、可解性、页结构（空白页/缺标题） |
| ✅ **模式B（含答案）** | 在模式A基础上逐题独立复算 + Python 程序验证 + 菁优网/学科网原题比对，判定：答案错误 / 答案不全 / 过程错误 / 存疑 |
| 🖍️ **可视化批注** | 红框 + 红字**直接写进 PDF 内容层**（任何阅读器/打印可见）：错在哪、正确答案是什么 |
| 📊 **可视化报告** | 单文件 HTML 报告：每题一张卡（题目小图 + 错因 + 正确答案 + 依据），图片 base64 内嵌，可直接发人 |
| 📏 **判定纪律** | **多解/答案不唯一 ≠ 错误**：只标🔵提示（蓝）；只有题目真错、答案真错、答案不全才标🔴（红） |

## 工作流

```
PDF ──extract/cut──► 每题小图 + 文本 + 题号链诊断
                         │
              ┌──────────┴──────────┐
        模式A(纯题目)            模式B(带答案)
        题干/题号/图文/可解性      + 手推 + 程序验证 + 原题比对
              └──────────┬──────────┘
                          ▼
        分级汇总(🔴错误/🟠存疑/🔵提示) ──► locate 定位 ──► 批注 PDF
                          ▼
              make_report ──► 报告.md + 报告.html
                          ▼
              run_regression ──► 改脚本后一键回归
```

## 安装

1. 下载 / clone 本仓库；
2. 把整个文件夹放进你的 skills 目录，例如：
   - Windows：`C:\Users\<你的用户名>\.cursor\skills\`
   - macOS / Linux：`~/.cursor/skills/`
3. 安装依赖（唯一必需项）：

```bash
pip install pymupdf
```

> OCR（扫描版试卷）、公式识别、整页转 Markdown 的可选工具链见 `references/toolchain.md`。

## 快速开始

```bash
# 1) 识别：全文 + 逐页图 + 题号链诊断
python scripts/extract_pdf.py 试卷.pdf -o 输出 --dpi 160

# 2) 题目级切图（逐题核对主力；跨页题自动拼接）
python scripts/cut_questions.py 试卷.pdf -o 输出/cut --merge

# 3) 批注定位（关键词→坐标，免手填）
python scripts/locate.py 试卷.pdf "变化而变" --page 3 --color red

# 4) 生成批注版 PDF（自动做宽度/越界/遮挡三重检查）
python scripts/draw_annotations.py --src 试卷.pdf --spec spec.json --dst 批注版.pdf --check-dir check

# 5) 生成报告（markdown + 单文件 HTML）
python scripts/make_report.py results.json -o 报告目录

# 6) 自测（可选：提供任意一份试卷跑全流程回归）
python scripts/run_regression.py --pdf 一份测试卷.pdf
```

## 脚本一览

| 脚本 | 作用 |
|---|---|
| `extract_pdf.py` | 文本层提取 + 逐页渲染 + 题号链诊断 + 区域裁剪 |
| `cut_questions.py` | **题目级自动切图**：题号锚定 + 几何并集 + 跨页题合并 |
| `locate.py` | **批注定位助手**：关键词 → 坐标 → spec JSON 片段 |
| `draw_annotations.py` | 批注引擎：画入 PDF 内容层；宽度/越界/遮挡三重检查 |
| `make_report.py` | 报告生成：markdown + 单文件 HTML（图片内嵌） |
| `verify_examples.py` | 6 类常考题的程序化验证模板（程序框图/数位整除/周期/集合/公式…） |
| `run_regression.py` | 12 项断言回归测试 |

## 判定标准（关键）

| 判定 | 含义 |
|---|---|
| 🔴 题目错误 | 题干错字/漏字/标点误用、题号错乱、图文不符、条件矛盾无解 |
| 🔴 答案错误 | 答案与正确结果不符 |
| 🔴 答案不全 | 题目多解但答案只写了部分情况 |
| 🟠 存疑 | 无法独立验证且查不到原题，待人工复核 |
| 🔵 提示 | **多解/答案不唯一（答案写全即为正确）**、表述可优化、易错提醒——**不算错误** |

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
