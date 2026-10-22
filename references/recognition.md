# 识别精度：原理、工具选型与取舍

> 目标：让"AI 看到的题"尽量等于"纸上的题"。本技能默认只用 **PyMuPDF + 几何/字体规则**（轻、快、离线），
> 重模型作为可选增强，按需安装。

---

## 一、PDF 识别的 6 个高频失真点

| 失真点 | 表现 | 本技能的处理 |
|---|---|---|
| 双栏/多栏 | 左右栏文字按 y 排序后串成一句，配图串栏 | `recognition.py` 用栏缝检测 + XY-cut 还原阅读顺序；切图按栏裁剪 |
| 阅读顺序 | 页眉/通栏标题/侧边注释混入正文 | XY-cut 先水平切（去掉通栏块）再垂直切（分栏） |
| 题号误判 | 选项 `A.`、小题 `（1）`、年份/页码被当题号 | 行首正则 + 栏内左边距 + 字号范围（6.5~22pt）+ 非选项/非小题 |
| 上下标/公式 | `a²+b²` 丢成 `a+b`，根号/分式变图 | 保留 span 级字号/上下标标记；公式区域转图人工核对；可选公式 OCR |
| 扫描件 | 无文本层，或文本层是错的旧 OCR | `ocr_pdf.py` 重新 OCR，输出低置信行清单 + 可检索 PDF |
| 图形/表格 | 图与题分离、跨页/跨栏 | 题目区域并集包含图片 bbox；跨页/跨栏自动拼接"合并图"并告警 |

## 二、内建版面算法（scripts/recognition.py）

1. **行提取**：`get_text("dict")` → 每行文本、bbox、最大字号、加粗、上下标标记；剔除页眉页脚。
2. **栏检测**：把页面横向离散化，统计"被某行跨过"的 x；在 30%~70% 宽度找最长空白带（≥10pt），
   要求左右各有 ≥4 行且纵向重叠 ≥80pt。大字号标题不参与（避免标题堵住栏缝）。
3. **阅读顺序**：递归 XY-cut。先找 ≥9pt 的横向空白切上下块，再找 ≥10pt 的纵向空白切左右栏；
   递归 6 层，兜底按 (y,x) 排序。
4. **题号锚定**：行首 `^\d{1,3}[.．、]`；x0 不超过该栏左边距 30pt；字号 6.5~22pt；排除选项/小题；
   纯题号行要求下一行同栏且间距 ≤32pt。
5. **版面告警**：无文本层、疑似漏检双栏、超小字号（<5.5pt）、同页同栏题号重复。

**已知边界**：三栏及以上、旋转文字、文字压图、题号在图形内（艺术字）仍可能失手；脚本会告警，必须回图复核。
误判双栏时用 `--no-columns` 强制单栏。

## 三、OCR 选型（扫描版）

| 引擎 | 许可 | 体积/速度 | 中文印刷体 | 适用 |
|---|---|---|---|---|
| **RapidOCR**（ONNX，PP-OCR 模型） | Apache-2.0 | ~80MB，CPU 快 | 好 | **默认推荐**，`pip install rapidocr-onnxruntime` |
| PaddleOCR 3.x / PP-OCRv5/v6 | Apache-2.0 | ~500MB，CPU 可用 | 最好 | 追求精度、可接受重依赖 |
| PaddleOCR-VL / PP-StructureV3 | Apache-2.0 | 需 GPU 更佳 | SOTA（含表格/公式/版面） | 整页结构化、复杂表格 |
| Tesseract 5 + chi_sim | Apache-2.0 | ~10MB | 一般 | 最轻量、离线兜底 |
| Surya | GPL-3.0 | 中 | 好（版面强） | 注意 GPL 传染性 |
| MinerU / marker / docling | 各自许可 | 重 | 好（PDF→Markdown） | 整本转换，不适合逐题精校 |

> 本技能只做"按行 OCR + 低置信标记"，不自动改写原文。OCR 数字（0/6、1/7、3/8、9/7）必须回图复核。

## 四、可选增强（按需，不默认安装）

- **版面检测模型**：DocLayout-YOLO、PP-StructureV3、中文试卷切题 YOLO 数据集（题目框检测）。
  适合版式极不规范、规则切题失败率高的场景；代价是模型/标注/部署。
- **公式识别**：pix2tex（LaTeX-OCR，MIT）、UniMERNet、PP-FormulaNet；把公式图转 LaTeX 再做文本比对。
- **答案等价判定**：huggingface/Math-Verify（MIT）可用于 `compare_answers.py` 的数值/符号等价扩展。
- **整页转 Markdown**：PyMuPDF4LLM、MinerU、marker；适合"先结构化再逐题"，但会丢失原坐标，批注仍需回原 PDF。

## 五、怎么验证"识别变准了"

用同一批 PDF 做 A/B，统计：

1. **题号召回**：切出的题号序列与人工标注的差异（漏题/多题/错号）。
2. **题目文本 CER**：本地文本 vs 人工转录的字符错误率（数字单独统计）。
3. **串栏率**：裁剪图中出现另一栏内容的题目比例。
4. **低置信占比**：OCR `low_confidence` 行数 / 总行数。
5. **下游收益**：进入"错误/存疑"的题中，因识别错误导致的误报比例。

建议保留 10~20 份不同版式（单栏/双栏/扫描/图文混排）的回归集，改算法后跑 `run_regression.py --pdf` 逐份回归。

## 六、许可提醒

- **PyMuPDF** 是 AGPL-3.0 / 商业双许可；闭源商用需购买商业授权。
- `pymupdf-layout` 为 Polyform Noncommercial，**不要**默认引入商业项目。
- Surya 为 GPL-3.0；PaddleOCR/RapidOCR 为 Apache-2.0；引用前请再次确认上游最新许可。

## 七、参考链接

- PyMuPDF 多栏阅读顺序工具：https://github.com/pymupdf/PyMuPDF-Utilities/blob/master/text-extraction/multi_column.py
- PaddleOCR 3.0 技术报告：https://arxiv.org/abs/2507.05595
- RapidOCR：https://github.com/RapidAI/RapidOCR
- Math-Verify：https://github.com/huggingface/Math-Verify
- LaTeX-OCR (pix2tex)：https://github.com/lukas-blecher/LaTeX-OCR
- DocLayout-YOLO：https://github.com/opendatalab/DocLayout-YOLO
- 中文试卷切题数据集（题目框/YOLO 标签）：GitHub topic `document-layout` / `question-segmentation`
