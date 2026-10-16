# PDF 识别工具链 与 GitHub 参考项目

优先用**已装好、无依赖负担**的方案；重型工具按需安装。

---

## 一、默认工具链（本技能已依赖，开箱即用）

### PyMuPDF —— 主力（文字层 + 渲染 + 批注一体）
- 文字层提取：`page.get_text()`（碎块多时用 `get_text("words")` 按坐标重组）
- 高DPI渲染看图：`page.get_pixmap(dpi=160~700, clip=Rect(x0,y0,x1,y1))`
- 局部裁剪放大（核对数字/字母）：见 `scripts/extract_pdf.py --crop`
- 批注写回：`page.draw_rect()` + `page.insert_text(fontname="china-s")`（中文字体内置）→ `scripts/draw_annotations.py`
- 安装：`pip install pymupdf`

**重要认知**：数学习题的公式、图形、程序框图常以图片或特殊字形存在，文本层不完整。**任何结论前必须看渲染图**。

---

## 二、扫描版 / 图片版 PDF（无文本层）

| 方案 | 特点 | 安装 |
|---|---|---|
| RapidOCR（推荐先用） | 离线中文 OCR，ONNX 无需 torch，轻 | `pip install rapidocr-onnxruntime` |
| PaddleOCR | 功能全（版面分析 PP-Structure）但依赖重 | `pip install paddleocr paddlepaddle` |
| Tesseract + chi_sim | 最轻但识别率一般 | 系统级安装 tesseract，配 `pytesseract` |

流程：先 `extract_pdf.py` 看 `report.txt` 里"无文本层页面"清单 → 对这些页渲染高DPI → OCR；**OCR 出的每个数字都要人工瞄一眼**（0/6、1/7、9/7 高发）。

---

## 三、公式 → LaTeX（需要公式级识别时）

| 方案 | 说明 | 链接 |
|---|---|---|
| pix2tex (LaTeX-OCR) | 公式截图→LaTeX，ViT，16k★ | github.com/lukas-blecher/LaTeX-OCR；`pip install pix2tex` |
| UniMERNet | 公式识别更全（含复杂版式） | github.com/opendatalab/UniMERNet |
| Mathpix API | 商业，最准，按量付费 | mathpix.com |

---

## 四、整页 PDF → Markdown（需要结构化时）

| 方案 | 说明 |
|---|---|
| MinerU（81k★） | PDF/Office → Markdown/JSON，版面分析+公式+表格；`pip install "mineru[core]"`（首次下载模型，体积大）github.com/opendatalab/MinerU |
| marker | VikParuchuri/marker，PDF→MD，效果稳定 |
| pdfplumber | 纯文字版表格型 PDF 的补充提取：`pip install pdfplumber` |

数学习题场景建议：**PyMuPDF 看图文为主，MinerU 仅在需要批量结构化成文本时使用。**

---

## 五、数学校验类项目

| 项目 | 说明 |
|---|---|
| huggingface/Math-Verify | 从模型输出抽取数学答案并判等价（LaTeX/数值），可借它的"答案等价判定"思路；偏竞赛英文，中文初中题仅作参考。链接：github.com/huggingface/Math-Verify（可选克隆到 `references/github/` 备查） |

---

## 六、菁优网相关开源工具（建议按需克隆到 `references/github/`）

| 项目 | 用途 | 仓库 |
|---|---|---|
| jyt2018/jyeoo-paper-formatter | 菁优网组卷页面→干净可打印试卷（bookmarklet / Python），无需会员 | github.com/jyt2018/jyeoo-paper-formatter |
| CodeZhangBorui/Jyeoo-Userscripts | 菁优打印处理 / 解限制油猴脚本 | github.com/CodeZhangBorui/Jyeoo-Userscripts |
| pengwow/web-crawler | 菁优网爬虫（Python，做题源批量获取参考） | github.com/pengwow/web-crawler |
| pengwow/jyeoo-crawler-gui | 菁优网图形化爬虫（已归档，仅参考） | github.com/pengwow/jyeoo-crawler-gui |

**合规提醒**：以上工具仅用于个人备课/校对查证；批量抓取注意目标站条款与频率限制，检索优先走搜索引擎摘要而非爬详情页。

---

## 七、安装速查

```bash
pip install pymupdf                 # 必备
pip install rapidocr-onnxruntime    # 扫描件OCR（可选）
pip install pix2tex                 # 公式→LaTeX（可选）
pip install "mineru[core]"          # 整页转MD（可选，重）
```
