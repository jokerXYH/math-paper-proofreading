# -*- coding: utf-8 -*-
"""技能一键自检 / 回归测试
=====================================================
默认使用**内置生成的迷你样卷**，零外部依赖，clone 下来即可运行：
  python scripts/run_regression.py

有私有黄金样卷时可加 --pdf 跑完整回归（含 34 题计数、跨页合并、错字命中）：
  python scripts/run_regression.py --pdf "示例-专题七/原稿.pdf"

检查项:
  1) extract_pdf      文本层/页数识别
  2) verify_examples  6 类程序化验证模板自检
  3) cut_questions    题目切分、答案区自动拆分、题号链诊断
  4) typo_scan        错字候选与 LLM 通读提示词
  5) draw_annotations 批注写入 + 宽度/越界检查 + 检查图
  6) align_answers    题目/答案分离对齐
  7) solver tasks     盲解任务书（题号去重）
  8) compare_answers  盲解交叉比对
  9) make_report      md + 单文件 HTML 报告
 10) validate_skill   技能结构与可用性自检

用法:
  python scripts/run_regression.py [--pdf 试卷.pdf] [--keep]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import pymupdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(HERE, ".."))
FIXTURES = os.path.join(SKILL_DIR, "tests", "fixtures")
OUT = os.path.join(SKILL_DIR, "tests", "out")

results = []   # (name, ok, detail)


def run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def check(name, ok, detail="", skip=False):
    if skip:
        results.append((name, None, detail))
        print(f"[SKIP] {name}" + (f"  —— {detail}" if detail else ""))
        return
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  —— {detail}" if detail and not ok else ""))


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def build_spec(path):
    """给迷你样卷生成一份最小批注规格（覆盖红框 + 红字 + 宽度检查）"""
    write_json(path, {
        "marks": [{"page": 1, "rect": [50, 175, 425, 198], "color": "red", "width": 1.6}],
        "notes": [{"page": 1, "x": 60, "y": 690, "size": 9, "color": "red",
                   "lines": ["▲示例批注：本题为技能自检样例，用于验证批注写入与宽度检查。"]}],
    })


def main():
    ap = argparse.ArgumentParser(description="技能自检 / 回归测试")
    ap.add_argument("--pdf", default=None, help="黄金样卷 PDF（可选）")
    ap.add_argument("--keep", action="store_true", help="保留中间产物（默认也保留）")
    args = ap.parse_args()

    golden = bool(args.pdf)
    py = sys.executable
    os.makedirs(OUT, exist_ok=True)

    # ---- 准备样卷 ----
    if golden:
        pdf = os.path.abspath(args.pdf)
        if not os.path.exists(pdf):
            print(f"找不到样卷: {pdf}")
            sys.exit(2)
    else:
        pdf = os.path.join(OUT, "_sample", "sample_exam.pdf")
        r = run([py, os.path.join(SKILL_DIR, "tests", "make_sample_pdf.py"), "-o", pdf])
        if r.returncode != 0 or not os.path.exists(pdf):
            print("生成内置样卷失败:", (r.stdout + r.stderr)[-500:])
            sys.exit(2)
        print("使用内置迷你样卷（零外部依赖）；私有黄金样卷请加 --pdf。")
    print(f"样卷: {pdf}\n输出: {OUT}\n")

    # ---- 1) extract_pdf ----
    ext = os.path.join(OUT, "extract")
    r = run([py, os.path.join(HERE, "extract_pdf.py"), pdf, "-o", ext, "--dpi", "60"])
    rep_p = os.path.join(ext, "report.txt")
    rep = open(rep_p, encoding="utf-8").read() if os.path.exists(rep_p) else ""
    check("1a extract_pdf 运行", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check("1b 识别到文本层", "文本层: 有" in rep, rep[:200])
    if golden:
        check("1c 检出题号回退 11 -> 7", "题号回退: 11 -> 7" in rep, rep[:300])
    else:
        check("1c 解析到 2 页", "页数: 2" in rep, rep[:200])

    # ---- 2) verify_examples ----
    r = run([py, os.path.join(HERE, "verify_examples.py")])
    check("2  verify_examples 模板自检",
          r.returncode == 0 and "全部模板自检通过" in r.stdout,
          (r.stdout + r.stderr)[-300:])

    # ---- 3) cut_questions ----
    cut = os.path.join(OUT, "cut")
    r = run([py, os.path.join(HERE, "cut_questions.py"), pdf, "-o", cut,
             "--dpi", "90", "--merge"])
    qs_p = os.path.join(cut, "questions.json")
    qs = json.load(open(qs_p, encoding="utf-8")) if os.path.exists(qs_p) else []
    crops = os.listdir(os.path.join(cut, "crops")) if os.path.isdir(os.path.join(cut, "crops")) else []
    expect_q = 34 if golden else 8
    check(f"3a 题目切分数量 = {expect_q}", len(qs) == expect_q, f"实际 {len(qs)}")
    qnos = [q["qno"] for q in qs]
    check("3b 题目题号无重复", len(qnos) == len(set(qnos)), str(qnos))
    if golden:
        merged = [c for c in crops if "合并" in c]
        check("3c 生成跨页合并图", len(merged) >= 1, str(crops[:5]))
        check("3d 题号诊断输出", "题号回退: 11 -> 7" in r.stdout, r.stdout[-200:])
    else:
        ans_p = os.path.join(cut, "answers.json")
        answers = json.load(open(ans_p, encoding="utf-8")) if os.path.exists(ans_p) else []
        check("3c 答案区自动拆分（8 条）", len(answers) == 8, f"实际 {len(answers)}")
        check("3d 答案题号 1~8 且未混入题目",
              [a["qno"] for a in answers] == list(range(1, 9)), str([a["qno"] for a in answers]))

    # ---- 4) typo_scan ----
    typo = os.path.join(OUT, "typo")
    r = run([py, os.path.join(HERE, "typo_scan.py"), pdf, "-o", typo])
    cand = os.path.join(typo, "typo_candidates.json")
    prompt = os.path.join(typo, "llm_review_prompt.md")
    check("4a 错字候选输出", os.path.exists(cand) and r.returncode == 0,
          (r.stdout + r.stderr)[-200:])
    check("4b 生成 LLM 通读提示词", os.path.exists(prompt))
    if golden:
        cand_txt = open(cand, encoding="utf-8").read() if os.path.exists(cand) else ""
        check("4c 命中『变化而变』（高）", "变化而变" in cand_txt and "高 1" in r.stdout,
              r.stdout[:300])

    # ---- 5) draw_annotations ----
    dst = os.path.join(OUT, "annotated.pdf")
    chk = os.path.join(OUT, "check")
    if golden:
        spec = os.path.join(FIXTURES, "spec_case1.json")
        expect_pages = 6
    else:
        spec = os.path.join(OUT, "spec_sample.json")
        build_spec(spec)
        expect_pages = 1
    r = run([py, os.path.join(HERE, "draw_annotations.py"),
             "--src", pdf, "--spec", spec, "--dst", dst,
             "--check-dir", chk, "--dpi", "90"])
    okw = "文字宽度检查: 全部通过" in r.stdout
    nowarn = "⚠" not in r.stdout and "自动折行" not in r.stdout
    nchk = len(os.listdir(chk)) if os.path.isdir(chk) else 0
    check("5a 批注生成 + 宽度检查全过", okw, r.stdout[-300:])
    check("5b 无超宽/遮挡/越界告警", nowarn, r.stdout[-300:])
    check(f"5c 检查图 {expect_pages} 页", nchk == expect_pages, f"实际 {nchk}")

    # ---- 6) align_answers ----
    ans_txt = os.path.join(OUT, "answers_sample.txt")
    if golden:
        open(ans_txt, "w", encoding="utf-8").write(
            "1. 231\n2. B（2）\n3. B（19）\n5. 10、8/3、2/9\n99. 多余答案\n")
        expect_pair, expect_extra = 4, 1
    else:
        open(ans_txt, "w", encoding="utf-8").write("1. A\n2. A\n99. 多余答案\n")
        expect_pair, expect_extra = 2, 1
    r = run([py, os.path.join(HERE, "align_answers.py"), pdf, ans_txt,
             "-o", os.path.join(OUT, "align")])
    check(f"6  答案分离对齐（配对{expect_pair}/多余{expect_extra}）",
          f"已配对: {expect_pair}" in r.stdout and f"多余答案: {expect_extra}" in r.stdout,
          r.stdout[-300:])

    # ---- 7) 盲解任务 ----
    tasks = os.path.join(OUT, "tasks")
    r = run([py, os.path.join(HERE, "make_solver_tasks.py"),
             qs_p, "-o", tasks, "--per-task", "8"])
    idx_p = os.path.join(tasks, "index.json")
    idx = json.load(open(idx_p, encoding="utf-8")) if os.path.exists(idx_p) else []
    all_qn = [q for it in idx for q in it["qn"]]
    check("7a 盲解任务书生成", len(idx) >= 1 and len(all_qn) == len(qs),
          f"任务 {len(idx)} 份，题 {len(all_qn)}")
    check("7b 任务题号无重复", len(all_qn) == len(set(all_qn)), str(all_qn))

    # ---- 8) compare_answers ----
    off_p = os.path.join(OUT, "official.json")
    sol_p = os.path.join(OUT, "solver.json")
    write_json(off_p, {"1": "A", "2": "A", "3": "B"})
    write_json(sol_p, {"1": "A", "2": "C", "3": "B"})
    r = run([py, os.path.join(HERE, "compare_answers.py"),
             "--official", off_p, "--solver", sol_p, "-o", os.path.join(OUT, "cmp")])
    check("8  盲解比对（1 处不一致→存疑）",
          "不一致 1" in r.stdout and "题2" in r.stdout, r.stdout[-300:])

    # ---- 9) make_report ----
    rep_dir = os.path.join(OUT, "report")
    os.makedirs(os.path.join(rep_dir, "crops"), exist_ok=True)
    src_crop = os.path.join(cut, "crops", "q_pg01_q01.png")
    if os.path.exists(src_crop):
        shutil.copy(src_crop, os.path.join(rep_dir, "crops", "case1_q07.png"))
    r = run([py, os.path.join(HERE, "make_report.py"),
             os.path.join(FIXTURES, "results_case1.json"), "-o", "."], cwd=rep_dir)
    html_p = os.path.join(rep_dir, "校对报告.html")
    md_p = os.path.join(rep_dir, "校对报告.md")
    html = open(html_p, encoding="utf-8").read() if os.path.exists(html_p) else ""
    check("9a 生成 md + html", os.path.exists(md_p) and os.path.exists(html_p),
          (r.stdout + r.stderr)[-300:])
    check("9b HTML 图片 base64 内嵌", "data:image/png;base64," in html)
    check("9c 统计正确（4 错误 / 4 提示）",
          "错误 4 处" in html and "提示 4 处" in html, html[:400])

    # ---- 10) 技能结构自检 ----
    r = run([py, os.path.join(HERE, "validate_skill.py")])
    check("10 validate_skill 技能自检", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    # ---- 11) 双栏版面：栏检测 + 分栏切题 + 不串栏 ----
    two_pdf = os.path.join(OUT, "_sample", "two_column.pdf")
    r = run([py, os.path.join(SKILL_DIR, "tests", "make_two_column_pdf.py"), "-o", two_pdf])
    two_ext = os.path.join(OUT, "two_extract")
    r = run([py, os.path.join(HERE, "extract_pdf.py"), two_pdf, "-o", two_ext, "--dpi", "60"])
    rep2 = open(os.path.join(two_ext, "report.txt"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(two_ext, "report.txt")) else ""
    check("11a 双栏版面识别", "版面:" in rep2 and "2栏" in rep2, rep2[:300])
    two_cut = os.path.join(OUT, "two_cut")
    r = run([py, os.path.join(HERE, "cut_questions.py"), two_pdf, "-o", two_cut, "--dpi", "80"])
    qs2_p = os.path.join(two_cut, "questions.json")
    qs2 = json.load(open(qs2_p, encoding="utf-8")) if os.path.exists(qs2_p) else []
    check("11b 双栏切出 6 题", len(qs2) == 6, f"实际 {len(qs2)}")
    cols = [q.get("column") for q in qs2]
    check("11c 左栏 1-3 / 右栏 4-6", cols == [0, 0, 0, 1, 1, 1], str(cols))
    cross = [q["qno"] for q in qs2 if q.get("rect") and (
        (q.get("column") == 0 and q["rect"][2] > 300) or
        (q.get("column") == 1 and q["rect"][0] < 300))]
    check("11d 裁剪不串栏", not cross, str(cross))

    # ---- 12) 差异定位：数字差异高优先，答案尾巴不误报 ----
    fake_search = os.path.join(OUT, "fake_search.json")
    write_json(fake_search, {"items": [
        {"qno": 3, "local_text": "3．若 a+b=5，ab=6，则 a²+b² 的值为（　　） "
                                 "A．11　B．13　C．15　D．17",
         "results": [{"source": "jyeoo", "title": "原题", "url": "https://example.com/1",
                      "snippet": "若 a+b=5，ab=7，则 a²+b² 的值为（　　） "
                                 "A．11　B．13　C．15　D．17", "score": 0.9}]},
        {"qno": 5, "local_text": "5．若 |x-2|=3，则 x=　　　　．",
         "results": [{"source": "jyeoo", "title": "原题", "url": "https://example.com/2",
                      "snippet": "若 |x-2|=3，则 x=5 或 x=-1．", "score": 0.85}]},
    ]})
    diff_dir = os.path.join(OUT, "diff")
    r = run([py, os.path.join(HERE, "diff_question.py"),
             "--originals", fake_search, "-o", diff_dir])
    diffs = json.load(open(os.path.join(diff_dir, "diff_results.json"),
                           encoding="utf-8"))["items"] \
        if os.path.exists(os.path.join(diff_dir, "diff_results.json")) else []
    d3 = next((x for x in diffs if x["qno"] == 3), {})
    d5 = next((x for x in diffs if x["qno"] == 5), {})
    check("12a 数字差异判为高优先",
          any(i["type"] == "数字不一致" and i["level"] == "high" for i in d3.get("issues", [])),
          str(d3.get("issues")))
    check("12b 原题尾部答案不误报关键差异",
          not any(i["level"] == "high" for i in d5.get("issues", [])), str(d5.get("issues")))

    # ---- 13) 可视化审阅台 ----
    review_html = os.path.join(OUT, "review.html")
    r = run([py, os.path.join(HERE, "make_review.py"),
             "--questions", qs_p, "--results", os.path.join(FIXTURES, "results_case1.json"),
             "--diff", os.path.join(diff_dir, "diff_results.json"),
             "--pages", os.path.join(ext, "pages"), "-o", review_html])
    html_txt = open(review_html, encoding="utf-8").read() if os.path.exists(review_html) else ""
    check("13a 审阅台生成", len(html_txt) > 20000, f"{len(html_txt)} 字符")
    check("13b 内嵌题目图与差异数据",
          "data:image/jpeg;base64," in html_txt and '"diff"' in html_txt)

    # ---- 14) 原题检索（离线模式，只生成链接） ----
    search_dir = os.path.join(OUT, "search")
    r = run([py, os.path.join(HERE, "search_original.py"),
             "--questions", qs_p, "--provider", "offline", "--limit-q", "2",
             "-o", search_dir])
    sr_p = os.path.join(search_dir, "search_results.json")
    sr = json.load(open(sr_p, encoding="utf-8")) if os.path.exists(sr_p) else {}
    check("14 原题检索离线清单", len(sr.get("items", [])) == 2 and
          os.path.exists(os.path.join(search_dir, "queries.md")),
          str(len(sr.get("items", []))))

    # ---- 15) OCR 兜底（有引擎才跑，否则跳过） ----
    import importlib.util
    has_ocr = any(importlib.util.find_spec(m) for m in
                  ("rapidocr_onnxruntime", "rapidocr", "paddleocr", "pytesseract"))
    if not has_ocr:
        check("15 OCR 兜底（未安装引擎，跳过）", True, skip=True)
    else:
        img_pdf = os.path.join(OUT, "_sample", "scanned.pdf")
        d = pymupdf.open(pdf)
        outd = pymupdf.open()
        for i, page in enumerate(d):
            pix = page.get_pixmap(dpi=120)
            img = os.path.join(OUT, f"_sample/scan_{i+1}.png")
            pix.save(img)
            pg = outd.new_page(width=page.rect.width, height=page.rect.height)
            pg.insert_image(pg.rect, filename=img)
        outd.save(img_pdf)
        outd.close()
        d.close()
        ocr_dir = os.path.join(OUT, "ocr")
        r = run([py, os.path.join(HERE, "ocr_pdf.py"), img_pdf, "-o", ocr_dir,
                 "--dpi", "200"])
        lines_p = os.path.join(ocr_dir, "lines.json")
        n_lines = len(json.load(open(lines_p, encoding="utf-8"))) \
            if os.path.exists(lines_p) else 0
        check("15 OCR 兜底生成文本层", n_lines > 0 and r.returncode == 0,
              (r.stdout + r.stderr)[-300:])

    # ---- 16) 三栏版面：1–4 栏通用检测 + 小数不误判 ----
    three_pdf = os.path.join(OUT, "_sample", "three_column.pdf")
    run([py, os.path.join(SKILL_DIR, "tests", "make_three_column_pdf.py"), "-o", three_pdf])
    three_ext = os.path.join(OUT, "three_extract")
    r = run([py, os.path.join(HERE, "extract_pdf.py"), three_pdf, "-o", three_ext, "--dpi", "60"])
    rep3 = open(os.path.join(three_ext, "report.txt"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(three_ext, "report.txt")) else ""
    three_cut = os.path.join(OUT, "three_cut")
    r = run([py, os.path.join(HERE, "cut_questions.py"), three_pdf, "-o", three_cut, "--dpi", "80"])
    qs3_p = os.path.join(three_cut, "questions.json")
    qs3 = json.load(open(qs3_p, encoding="utf-8")) if os.path.exists(qs3_p) else []
    check("16a 三栏版面识别", "3栏" in rep3, rep3[:300])
    check("16b 三栏切出 6 题且无 0 号",
          [q["qno"] for q in qs3] == [1, 2, 3, 4, 5, 6],
          str([q["qno"] for q in qs3]))
    check("16c 栏归属 0,0,1,1,2,2",
          [q.get("column") for q in qs3] == [0, 0, 1, 1, 2, 2],
          str([q.get("column") for q in qs3]))
    bad = []
    for q in qs3:
        cx = (q["rect"][0] + q["rect"][2]) / 2
        third = 0 if cx < 280 else (1 if cx < 561 else 2)
        if third != q.get("column"):
            bad.append(q["qno"])
    check("16d 三栏裁剪不串栏", not bad, str(bad))

    # ---- 汇总 ----
    print("\n" + "=" * 60)
    fails = [n for n, ok, _ in results if ok is False]
    skips = [n for n, ok, _ in results if ok is None]
    passed = len([1 for _, ok, _ in results if ok is True])
    if fails:
        print(f"回归结果: {passed} 通过 / {len(fails)} 失败 / {len(skips)} 跳过")
        print("失败项:", fails)
        sys.exit(1)
    print(f"回归结果: 全部 {passed} 项通过 ✔"
          + (f"（{len(skips)} 项跳过）" if skips else "")
          + ("（黄金样卷）" if golden else "（内置样卷）"))
    print(f"中间产物: {OUT}（下次运行会覆盖）")


if __name__ == "__main__":
    main()
