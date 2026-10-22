# -*- coding: utf-8 -*-
"""扫描版 / 图片版试卷 OCR 兜底（可选依赖，按需安装）
=====================================================
把没有文本层的 PDF 转成"可检索 PDF + 逐行 JSON"，后续 cut_questions 可直接使用。

引擎（自动按可用性选择，也可 --engine 指定）:
  rapidocr   pip install rapidocr-onnxruntime   （推荐：ONNX、CPU 快、中文好、约 80MB）
  paddleocr  pip install paddleocr paddlepaddle （精度最高、体积大）
  tesseract  安装 Tesseract + pip install pytesseract （最轻、精度一般）

用法:
  python ocr_pdf.py 扫描卷.pdf -o 输出/ocr                    # 自动选引擎
  python ocr_pdf.py 扫描卷.pdf -o 输出/ocr --engine rapidocr --dpi 300
  python ocr_pdf.py 扫描卷.pdf -o 输出/ocr --no-pdf           # 只出 JSON/文本

输出:
  ocr/text.txt                 按阅读顺序的全文
  ocr/lines.json               每行 {page,text,bbox,score,low_confidence}
  ocr/pages/page_XX.json       分页原始结果
  ocr/试卷_ocr.pdf             带隐形文本层的 PDF（可直接喂给 cut_questions）
  ocr/report.txt               引擎/页数/低置信行统计

纪律: OCR 出来的数字（0/6、1/7、3/8、9/7）必须回渲染图复核后再进结论。
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

LOW_SCORE = 0.80
LOW_DIGIT_SCORE = 0.90
DIGIT_RE = re.compile(r"\d")


def _engine_rapidocr():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except ImportError:
        try:
            from rapidocr import RapidOCR  # type: ignore
        except ImportError:
            return None
    eng = RapidOCR()

    def run(img_path):
        out = eng(img_path)
        lines = []
        # 旧版: (result, elapse)，result=[[box, text, score], ...]
        if isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], list):
            for box, text, score in out[0]:
                lines.append(_from_box(box, text, score))
            return lines
        # 新版: 对象带 boxes/txts/scores
        boxes = getattr(out, "boxes", None)
        txts = getattr(out, "txts", None)
        scores = getattr(out, "scores", None)
        if boxes is not None and txts is not None:
            for box, text, score in zip(boxes, txts, scores):
                lines.append(_from_box(box, text, float(score)))
            return lines
        raise RuntimeError("无法解析 RapidOCR 返回格式，请升级 rapidocr 或改用 --engine paddleocr")
    return run


def _engine_paddleocr():
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except ImportError:
        return None
    try:
        eng = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    except TypeError:
        eng = PaddleOCR(lang="ch")

    def run(img_path):
        lines = []
        if hasattr(eng, "ocr"):
            try:
                res = eng.ocr(img_path, cls=True)
            except TypeError:
                res = eng.ocr(img_path)
            for page in (res or []):
                for item in (page or []):
                    box, (text, score) = item[0], item[1]
                    lines.append(_from_box(box, text, float(score)))
            return lines
        out = eng.predict(img_path)   # PaddleOCR 3.x
        for r in out:
            boxes = r.get("rec_boxes") or r.get("dt_polys")
            texts = r.get("rec_texts")
            scores = r.get("rec_scores")
            for box, text, score in zip(boxes, texts, scores):
                lines.append(_from_box(box, text, float(score)))
        return lines
    return run


def _engine_tesseract():
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        return None

    def run(img_path):
        data = pytesseract.image_to_data(Image.open(img_path), lang="chi_sim+eng",
                                         output_type=pytesseract.Output.DICT)
        grouped = {}
        for i, txt in enumerate(data["text"]):
            if not txt.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped.setdefault(key, []).append((txt, int(data["conf"][i]),
                                                data["left"][i], data["top"][i],
                                                data["width"][i], data["height"][i]))
        lines = []
        for key in sorted(grouped):
            items = grouped[key]
            text = "".join(t for t, *_ in items)
            conf = sum(c for _, c, *_ in items) / max(1, len(items)) / 100.0
            x0 = min(i[2] for i in items)
            y0 = min(i[3] for i in items)
            x1 = max(i[2] + i[4] for i in items)
            y1 = max(i[3] + i[5] for i in items)
            lines.append({"text": text, "box": [x0, y0, x1, y1], "score": round(conf, 3)})
        return lines
    return run


ENGINES = [("rapidocr", _engine_rapidocr), ("paddleocr", _engine_paddleocr),
           ("tesseract", _engine_tesseract)]


def _from_box(box, text, score):
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return {"text": str(text).strip(), "box": [min(xs), min(ys), max(xs), max(ys)],
            "score": round(float(score), 3)}


def pick_engine(name):
    for n, factory in ENGINES:
        if name != "auto" and n != name:
            continue
        fn = factory()
        if fn:
            return n, fn
    return None, None


def main():
    ap = argparse.ArgumentParser(description="扫描版试卷 OCR")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", default="ocr_out")
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "rapidocr", "paddleocr", "tesseract"])
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--no-pdf", action="store_true", help="不生成带文本层的 PDF")
    ap.add_argument("--force", action="store_true", help="已有文本层也重新 OCR")
    args = ap.parse_args()

    name, run = pick_engine(args.engine)
    if not run:
        print("未找到可用的 OCR 引擎。请任选一个安装：\n"
              "  pip install rapidocr-onnxruntime     # 推荐\n"
              "  pip install paddleocr paddlepaddle\n"
              "  pip install pytesseract pillow  + 安装 Tesseract 及 chi_sim 语言包")
        sys.exit(2)

    doc = pymupdf.open(args.pdf)
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, "pages"), exist_ok=True)
    img_dir = os.path.join(args.out, "images")
    os.makedirs(img_dir, exist_ok=True)

    all_lines, report, low_total = [], [], 0
    for i, page in enumerate(doc):
        pno = i + 1
        if page.get_text().strip() and not args.force:
            continue   # 已有文本层，跳过
        pix = page.get_pixmap(dpi=args.dpi)
        img_path = os.path.join(img_dir, f"page_{pno:02d}.png")
        pix.save(img_path)
        raw = run(img_path)
        scale = 72.0 / args.dpi
        lines = []
        for ln in raw:
            t = ln["text"]
            if not t:
                continue
            x0, y0, x1, y1 = [v * scale for v in ln["box"]]
            low = bool(ln["score"] < LOW_SCORE or (
                DIGIT_RE.search(t) and ln["score"] < LOW_DIGIT_SCORE))
            item = {"page": pno, "text": t, "bbox": [round(x0, 1), round(y0, 1),
                                                     round(x1, 1), round(y1, 1)],
                    "score": ln["score"], "low_confidence": low}
            lines.append(item)
            all_lines.append(item)
            low_total += int(low)
        lines.sort(key=lambda x: (round(x["bbox"][1], 1), x["bbox"][0]))
        with open(os.path.join(args.out, "pages", f"page_{pno:02d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(lines, f, ensure_ascii=False, indent=1)
        report.append(f"第{pno}页: {len(lines)} 行，低置信 {sum(1 for x in lines if x['low_confidence'])} 行")

    with open(os.path.join(args.out, "lines.json"), "w", encoding="utf-8") as f:
        json.dump(all_lines, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "text.txt"), "w", encoding="utf-8") as f:
        cur = None
        for ln in all_lines:
            if cur != ln["page"]:
                cur = ln["page"]
                f.write(f"\n===== 第{cur}页 =====\n")
            f.write(ln["text"] + "\n")

    # 生成带隐形文本层的 PDF，方便后续按题号切分
    if not args.no_pdf:
        out_doc = pymupdf.open()
        for i, page in enumerate(doc):
            pno = i + 1
            out_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            img = os.path.join(img_dir, f"page_{pno:02d}.png")
            if os.path.exists(img):
                out_page.insert_image(out_page.rect, filename=img)
                for ln in [x for x in all_lines if x["page"] == pno]:
                    x0, y0, x1, y1 = ln["bbox"]
                    size = max(5.0, min(14.0, (y1 - y0) * 0.82))
                    out_page.insert_text((x0, y1 - (y1 - y0) * 0.18), ln["text"],
                                         fontsize=size, fontname="china-s",
                                         render_mode=3)
            else:
                out_page.show_pdf_page(out_page.rect, doc, i)
        out_pdf = os.path.join(args.out,
                               os.path.splitext(os.path.basename(args.pdf))[0] + "_ocr.pdf")
        out_doc.save(out_pdf)
        out_doc.close()
        report.append(f"可检索 PDF: {out_pdf}")

    header = [f"引擎: {name}", f"页数: {len(doc)}",
              f"OCR 行数: {len(all_lines)}", f"低置信行: {low_total}（需回图复核）"]
    if all_lines:
        avg = sum(x["score"] for x in all_lines) / len(all_lines)
        ratio = low_total / len(all_lines)
        header.append(f"平均置信度: {avg:.2f}")
        if ratio > 0.5 or avg < 0.6:
            header.append("⚠ 低置信占比过高，疑似手写/拍照/低清扫描：OCR 结果不可直接用于校对，"
                          "请人工转录或换更清晰的扫描件")
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(header + report))
    print("\n".join(header + report))


if __name__ == "__main__":
    main()
