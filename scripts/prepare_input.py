# -*- coding: utf-8 -*-
"""把各种输入统一成 PDF（图片 / DOCX / 图片文件夹 → PDF）。

用法:
  python prepare_input.py 试卷.docx -o 输出/input
  python prepare_input.py 扫描件目录/ -o 输出/input --name 试卷.pdf
  python prepare_input.py 试卷.pdf -o 输出/input          # 已是 PDF：直接复制

支持:
  .pdf                      直接复制（不重复处理）
  .png .jpg .jpeg .webp .bmp .tif .tiff
                            单张 → 单页 PDF；目录 → 按文件名自然排序合并
  .docx .doc                LibreOffice 或 Microsoft Word 转 PDF（需本机已安装）

输出:
  <out>/<name>.pdf          后续脚本统一用它（extract_pdf / cut_questions …）

依赖: pymupdf（图片转 PDF、页数校验）；DOCX 转换依赖本机 Office/LibreOffice。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import pymupdf
except ImportError:  # 允许先看 --help
    pymupdf = None

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
DOC_EXT = {".docx", ".doc"}
A4 = (595, 842)


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def images_to_pdf(paths, out_path):
    if pymupdf is None:
        sys.exit("缺少 pymupdf：pip install pymupdf")
    doc = pymupdf.open()
    for p in paths:
        img = pymupdf.open(p)
        w, h = img[0].rect.width, img[0].rect.height
        # 按 A4 等比缩放并居中，避免超页/变形
        scale = min(A4[0] / w, A4[1] / h)
        page = doc.new_page(width=A4[0], height=A4[1])
        tw, th = w * scale, h * scale
        rect = pymupdf.Rect((A4[0] - tw) / 2, (A4[1] - th) / 2,
                            (A4[0] + tw) / 2, (A4[1] + th) / 2)
        page.insert_image(rect, filename=p)
        img.close()
    doc.save(out_path)
    doc.close()


def find_soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p):
            return p
    return None


def docx_to_pdf(src, out_dir):
    soffice = find_soffice()
    if soffice:
        r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", out_dir, src],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        out = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
        if r.returncode == 0 and os.path.exists(out):
            return out
        raise RuntimeError((r.stdout + r.stderr).strip()[:300] or "LibreOffice 转换失败")

    if os.name == "nt":
        try:
            import win32com.client  # type: ignore
        except ImportError:
            raise RuntimeError(
                "未找到 LibreOffice，也未安装 pywin32。请任选其一：\n"
                "  1) 安装 LibreOffice（https://www.libreoffice.org/）\n"
                "  2) pip install pywin32（用本机 Word 转换）\n"
                "  3) 在 Word 中手动「另存为 PDF」后再跑本工具")
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        try:
            doc = word.Documents.Open(os.path.abspath(src), ReadOnly=True)
            out = os.path.join(os.path.abspath(out_dir),
                               os.path.splitext(os.path.basename(src))[0] + ".pdf")
            doc.SaveAs(out, FileFormat=17)   # wdFormatPDF
            doc.Close(False)
            return out
        finally:
            word.Quit()

    raise RuntimeError("DOC/DOCX 转换需要 LibreOffice 或本机 Word：请先另存为 PDF")


def main():
    ap = argparse.ArgumentParser(description="把图片/DOCX/文件夹统一转换成 PDF")
    ap.add_argument("input", help="PDF / 图片 / 图片文件夹 / DOCX")
    ap.add_argument("-o", "--out", default="input_pdf", help="输出目录")
    ap.add_argument("--name", default=None, help="输出文件名（默认沿用输入名）")
    args = ap.parse_args()

    src = os.path.abspath(args.input)
    if not os.path.exists(src):
        sys.exit(f"输入不存在: {src}")
    os.makedirs(args.out, exist_ok=True)
    name = args.name or (os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    dst = os.path.join(os.path.abspath(args.out), name)

    ext = os.path.splitext(src)[1].lower()
    if os.path.isdir(src):
        paths = [os.path.join(src, f) for f in sorted(os.listdir(src), key=natural_key)
                 if os.path.splitext(f)[1].lower() in IMAGE_EXT]
        if not paths:
            sys.exit(f"目录里没有可用图片: {src}")
        images_to_pdf(paths, dst)
        print(f"合并 {len(paths)} 张图片 → {dst}")
    elif ext == ".pdf":
        if os.path.abspath(dst) != src:
            shutil.copyfile(src, dst)
        print(f"已是 PDF → {dst}")
    elif ext in IMAGE_EXT:
        images_to_pdf([src], dst)
        print(f"图片 → {dst}")
    elif ext in DOC_EXT:
        tmp = docx_to_pdf(src, os.path.abspath(args.out))
        if os.path.abspath(tmp) != os.path.abspath(dst):
            os.replace(tmp, dst)
        print(f"DOCX → {dst}")
    else:
        sys.exit(f"不支持的输入类型: {ext}（支持 PDF / 图片 / DOCX）")

    doc = pymupdf.open(dst)
    print(f"页数: {len(doc)}　后续请用: python scripts/extract_pdf.py {dst} -o 输出")
    doc.close()


if __name__ == "__main__":
    main()
