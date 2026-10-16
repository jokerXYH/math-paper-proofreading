# -*- coding: utf-8 -*-
"""批量回归测试（P0-4）
=====================================================
用"示例-专题七"跑一遍全流程，逐项断言，输出 PASS/FAIL。
每次改完脚本后运行一次，防止改坏已有能力。

用法:
  python run_regression.py                # 默认用 ../../示例-专题七/原稿.pdf
  python run_regression.py --pdf 其他试卷.pdf [--keep]  # --keep 保留中间产物

检查项:
  1) extract_pdf   能识别文本层、检出"题号回退 11 -> 7"
  2) verify_examples 模板自检全过
  3) cut_questions 切出 34 题、生成跨页合并图、题号诊断正确
  4) draw_annotations 宽度检查全过、无告警、6 页检查图生成
  5) make_report   生成 md+html，图片内嵌成功
"""
import argparse
import os
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(HERE, ".."))
CASE_DIR = os.path.normpath(os.path.join(SKILL_DIR, "..", "示例-专题七"))
FIXTURES = os.path.join(SKILL_DIR, "tests", "fixtures")
OUT = os.path.join(SKILL_DIR, "tests", "out")

results = []


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=cwd)
    return r


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    icon = "PASS" if ok else "FAIL"
    print(f"[{icon}] {name}" + (f"  —— {detail}" if detail and not ok else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=os.path.join(CASE_DIR, "原稿.pdf"))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    py = sys.executable
    pdf = args.pdf
    if not os.path.exists(pdf):
        print(f"找不到样例PDF: {pdf}")
        sys.exit(2)
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    print(f"样例: {pdf}\n输出: {OUT}\n")

    # ---- 1) extract_pdf ----
    ext = os.path.join(OUT, "extract")
    r = run([py, os.path.join(HERE, "extract_pdf.py"), pdf, "-o", ext, "--dpi", "60"])
    rep = open(os.path.join(ext, "report.txt"), encoding="utf-8").read() if os.path.exists(os.path.join(ext, "report.txt")) else ""
    check("1a extract_pdf 运行", r.returncode == 0, r.stderr[:200])
    check("1b 检出题号回退 11 -> 7", "题号回退: 11 -> 7" in rep, rep[:200])

    # ---- 2) verify_examples ----
    r = run([py, os.path.join(HERE, "verify_examples.py")])
    check("2  verify_examples 模板自检", r.returncode == 0 and "全部模板自检通过" in r.stdout,
          (r.stdout + r.stderr)[-300:])

    # ---- 3) cut_questions ----
    cut = os.path.join(OUT, "cut")
    r = run([py, os.path.join(HERE, "cut_questions.py"), pdf, "-o", cut, "--dpi", "90", "--merge"])
    crops = os.listdir(os.path.join(cut, "crops")) if os.path.isdir(os.path.join(cut, "crops")) else []
    merged = [c for c in crops if "合并" in c]
    check("3a 切出题目数 = 34", len([c for c in crops if not c.endswith("合并.png")]) == 34,
          f"实际 {len(crops)} 个文件")
    check("3b 生成跨页合并图（题5→第2页）", len(merged) >= 1, str(crops[:5]))
    check("3c 题号诊断输出", "题号回退: 11 -> 7" in r.stdout, r.stdout[-200:])

    # ---- 4) draw_annotations ----
    dst = os.path.join(OUT, "annotated.pdf")
    chk = os.path.join(OUT, "check")
    r = run([py, os.path.join(HERE, "draw_annotations.py"),
             "--src", pdf, "--spec", os.path.join(FIXTURES, "spec_case1.json"),
             "--dst", dst, "--check-dir", chk, "--dpi", "90"])
    okw = "文字宽度检查: 全部通过" in r.stdout
    nowarn = "⚠" not in r.stdout and "自动折行" not in r.stdout
    nchk = len(os.listdir(chk)) if os.path.isdir(chk) else 0
    check("4a 批注生成+宽度检查全过", okw, r.stdout[-300:])
    check("4b 无超宽/遮挡/越界告警", nowarn, r.stdout)
    check("4c 检查图 6 页", nchk == 6, f"实际 {nchk}")

    # ---- 5) make_report ----
    rep_dir = os.path.join(OUT, "report")
    os.makedirs(os.path.join(rep_dir, "crops"), exist_ok=True)
    src_crop = os.path.join(cut, "crops", "q_pg06_q07.png")
    if os.path.exists(src_crop):
        shutil.copy(src_crop, os.path.join(rep_dir, "crops", "case1_q07.png"))
    r = run([py, os.path.join(HERE, "make_report.py"),
             os.path.join(FIXTURES, "results_case1.json"), "-o", "."],
            cwd=rep_dir)
    html_p = os.path.join(rep_dir, "校对报告.html")
    md_p = os.path.join(rep_dir, "校对报告.md")
    html = open(html_p, encoding="utf-8").read() if os.path.exists(html_p) else ""
    check("5a 生成 md + html", os.path.exists(md_p) and os.path.exists(html_p), r.stdout + r.stderr)
    check("5b HTML 图片 base64 内嵌", "data:image/png;base64," in html)
    check("5c 统计正确（4错误/4提示）", "错误 4 处" in html and "提示 4 处" in html, html[:500])

    # ---- 6) align_answers（P1-6 答案分离对齐）----
    ans_txt = os.path.join(OUT, "answers_sample.txt")
    open(ans_txt, "w", encoding="utf-8").write(
        "1. 231\n2. B（2）\n3. B（19）\n5. 10、8/3、2/9\n99. 多余答案\n")
    r = run([py, os.path.join(HERE, "align_answers.py"), pdf, ans_txt,
             "-o", os.path.join(OUT, "align")])
    check("6a 答案分离对齐（配对4/多余1）",
          "已配对: 4" in r.stdout and "多余答案: 1" in r.stdout, r.stdout[-300:])

    # ---- 7) 第二解题者（P1-7 任务生成+比对）----
    r = run([py, os.path.join(HERE, "make_solver_tasks.py"),
             os.path.join(cut, "questions.json"), "-o", os.path.join(OUT, "tasks")])
    ntask = len([f for f in os.listdir(os.path.join(OUT, "tasks")) if f.startswith("task_")]) \
        if os.path.isdir(os.path.join(OUT, "tasks")) else 0
    check("7a 盲解任务书生成（5份）", ntask == 5, f"实际 {ntask}")
    off_p = os.path.join(OUT, "official.json")
    sol_p = os.path.join(OUT, "solver.json")
    open(off_p, "w", encoding="utf-8").write('{"1":"231","2":"B(2)","3":"B(19)","5":"8/3、2/9、10"}')
    open(sol_p, "w", encoding="utf-8").write('{"1":"231","2":"B(2)","3":"D","5":"10、8/3、2/9"}')
    r = run([py, os.path.join(HERE, "compare_answers.py"),
             "--official", off_p, "--solver", sol_p, "-o", os.path.join(OUT, "cmp")])
    check("7b 盲解比对（1处不一致→存疑）",
          "不一致 1" in r.stdout and "题3" in r.stdout, r.stdout[-300:])

    # ---- 8) typo_scan（P1-8 错别字筛查）----
    r = run([py, os.path.join(HERE, "typo_scan.py"), pdf, "-o", os.path.join(OUT, "typo")])
    cand = os.path.join(OUT, "typo", "typo_candidates.json")
    prompt = os.path.join(OUT, "typo", "llm_review_prompt.md")
    cand_txt = open(cand, encoding="utf-8").read() if os.path.exists(cand) else ""
    check("8a 筛查到『变化而变』（高）", "变化而变" in cand_txt and "高 1" in r.stdout, r.stdout[:400])
    check("8b 生成 LLM 通读提示词", os.path.exists(prompt))

    # ---- 汇总 ----
    print("\n" + "=" * 60)
    fails = [n for n, ok, _ in results if not ok]
    if fails:
        print(f"回归结果: {len(results) - len(fails)}/{len(results)} 通过，失败项: {fails}")
        sys.exit(1)
    print(f"回归结果: 全部 {len(results)} 项通过 ✔（用例: 示例-专题七）")
    if not args.keep:
        print(f"中间产物保留在: {OUT}（下次运行会清空）")


if __name__ == "__main__":
    main()
