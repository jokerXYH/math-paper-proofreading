# -*- coding: utf-8 -*-
"""技能结构与可用性自检（打包/发版前跑一遍）。

用法:
  python scripts/validate_skill.py [--skill-dir 技能根目录]

检查:
  1) SKILL.md 存在，frontmatter 合法（name / description）
  2) name 与目录名一致，description 长度符合技能规范（<=1024 字符）
  3) SKILL.md 里引用的 references/scripts 文件都存在
  4) 所有脚本语法可编译，--help 可正常执行
  5) 依赖 pymupdf 可导入（缺失只警告）
  6) 仓库干净：无 tests/out、__pycache__、references/github/.git 等运行产物
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.normpath(os.path.join(HERE, ".."))
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LIB_MODULES = {"recognition.py"}   # 纯库模块，不要求 --help

errors, warns = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def parse_frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return None
    data = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def main():
    ap = argparse.ArgumentParser(description="技能结构与可用性自检")
    ap.add_argument("--skill-dir", default=DEFAULT_ROOT)
    args = ap.parse_args()
    root = os.path.abspath(args.skill_dir)

    # ---- 1) SKILL.md ----
    skill_path = os.path.join(root, "SKILL.md")
    if not os.path.exists(skill_path):
        err("缺少 SKILL.md")
        report()
        return
    text = open(skill_path, encoding="utf-8").read()
    fm = parse_frontmatter(text)
    if fm is None:
        err("SKILL.md frontmatter 缺失（应为 --- 包裹的 YAML）")
        fm = {}
    name = fm.get("name", "")
    desc = fm.get("description", "")
    if not name:
        err("frontmatter 缺少 name")
    elif not NAME_RE.match(name):
        err(f"name 不合法（小写字母/数字/连字符）: {name!r}")
    elif name != os.path.basename(root):
        warn(f"name({name}) 与目录名({os.path.basename(root)}) 不一致")
    if not desc:
        err("frontmatter 缺少 description")
    else:
        if len(desc) > 1024:
            err(f"description 过长: {len(desc)} 字符（上限 1024）")
        if len(desc) < 40:
            warn(f"description 偏短（{len(desc)} 字符），可能不容易被触发")

    # ---- 2) 引用完整性 ----
    for link in re.findall(r"\]\(([^)]+)\)", text):
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = os.path.join(root, link.split("#")[0])
        if not os.path.exists(target):
            err(f"SKILL.md 引用不存在: {link}")
    for ref in re.findall(r"`(scripts/[A-Za-z0-9_\-./]+)`", text):
        if not os.path.exists(os.path.join(root, ref)):
            err(f"SKILL.md 提到的脚本不存在: {ref}")

    # ---- 3) 脚本编译 + --help ----
    scripts_dir = os.path.join(root, "scripts")
    if not os.path.isdir(scripts_dir):
        err("缺少 scripts/ 目录")
    else:
        for fn in sorted(os.listdir(scripts_dir)):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(scripts_dir, fn)
            try:
                compile(open(path, encoding="utf-8").read(), path, "exec")
            except SyntaxError as e:
                err(f"语法错误 {fn}: {e}")
                continue
            if fn in LIB_MODULES:      # 纯库模块没有 CLI
                continue
            r = subprocess.run([sys.executable, path, "--help"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60)
            if r.returncode != 0:
                err(f"--help 失败 {fn}: {(r.stderr or r.stdout).strip()[:200]}")

    # ---- 4) 依赖 ----
    if importlib.util.find_spec("pymupdf") is None:
        warn("未安装 pymupdf（pip install pymupdf），PDF 相关脚本无法运行")
    else:
        r = subprocess.run([sys.executable, "-c", "import pymupdf; print(pymupdf.__version__)"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode == 0:
            print(f"pymupdf 版本: {r.stdout.strip()}")

    # ---- 5) 仓库卫生 ----
    junk = []
    for base, dirs, files in os.walk(root):
        rel = os.path.relpath(base, root)
        if rel.startswith("references" + os.sep + "github"):
            junk.append(rel + os.sep + "(第三方克隆)")
            dirs[:] = []
            continue
        for d in list(dirs):
            if d in (".pytest_cache",):
                junk.append(os.path.join(rel, d))
                dirs.remove(d)
        if os.path.basename(base) == "out" and os.path.basename(os.path.dirname(base)) == "tests":
            junk.append(rel)
            dirs[:] = []
    if junk:
        warn("发现运行产物/外部克隆（打包前应清理）: " + ", ".join(sorted(set(junk))[:8]))

    report()


def report():
    if warns:
        print("\n[WARN]")
        for w in warns:
            print("  -", w)
    if errors:
        print("\n[FAIL]")
        for e in errors:
            print("  -", e)
        print(f"\n自检未通过：{len(errors)} 个错误，{len(warns)} 个警告")
        sys.exit(1)
    print(f"\n技能自检通过 ✔（{len(warns)} 个警告）")


if __name__ == "__main__":
    main()
