# -*- coding: utf-8 -*-
"""原题线索检索（找参考答案、命题意图、条件是否漏）
=====================================================
用途：为每道题找"可能的原题/官方答案"作为参考。
注意：**题目允许改编**，本地题干与网上原题不同不是错误；最终必须按本地题重算并用
verify_answer.py 验证答案。

支持来源（--provider，可多选）:
  bing        必应网页搜索（无需 Key）
  duckduckgo  DuckDuckGo HTML 版（无需 Key）
  jyeoo       菁优网站内搜索（需登录 Cookie，见下）
  offline     不联网：只生成可点击的检索链接，交人工/AI 浏览器核查

菁优网 Cookie（可选）:
  set JYEOO_COOKIE=...        # Windows PowerShell: $env:JYEOO_COOKIE="..."
  或在 config.json 里写 {"jyeoo_cookie": "..."}

用法:
  python search_original.py --questions 输出/cut/questions.json -o 输出/search
  python search_original.py --text "若 a+b=5，ab=6，则 a²+b² 的值为" --provider bing
  python search_original.py --questions ... --provider offline       # 只出链接
  python search_original.py --questions ... --fetch-top 2            # 抓取前2条正文

输出:
  search/search_results.json   每条题目的候选原题（标题/链接/摘要/相似度）
  search/queries.md            人工可点的检索清单

纪律:
  - 默认每题每源只查 1 次，带缓存与 1.2s 间隔，请勿批量高频抓取；
  - 抓取结果页前会检查 robots.txt（--no-robots 可关闭，但请自行确认授权）；
  - 检索结果只是候选，必须点开原题核对题干/答案后才能作为证据。
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from urllib import robotparser
from difflib import SequenceMatcher
from html.parser import HTMLParser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache",
                         "math-paper-proofreading", "search")
CACHE_TTL = 7 * 86400
DELAY = 1.2
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


# ---------------- 文本处理 ----------------
def clean_text(s):
    s = html.unescape(TAG_RE.sub("", s or ""))
    return WS_RE.sub(" ", s).strip()


def norm(s):
    tr = {"（": "(", "）": ")", "，": ",", "、": ",", "：": ":", "；": ";",
          "．": ".", "　": " ", "－": "-", "−": "-", "×": "*", "÷": "/",
          "≤": "<=", "≥": ">=", "≠": "!="}
    for a, b in tr.items():
        s = s.replace(a, b)
    return WS_RE.sub("", s).lower()


def stem_of(text):
    """题目正文 → 检索用的题干（去掉题号、选项、答案区）。"""
    lines = []
    for raw in (text or "").splitlines():
        t = raw.strip()
        if not t:
            continue
        if re.match(r"^[A-DＡ-Ｄ]\s*[.．、]", t):
            continue
        if re.match(r"^(参考答案|答案|解析|【答案】)", t):
            break
        t = re.sub(r"^\s*\d{1,3}\s*[.．、]\s*", "", t)
        lines.append(t)
    s = " ".join(lines)
    s = re.sub(r"[（(]\s*[）)]", " ", s)          # 空括号
    s = re.sub(r"\s+", " ", s).strip()
    return s[:90]


def similarity(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 3)


# ---------------- HTTP ----------------
def http_get(url, timeout=20, headers=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        "Accept-Encoding": "gzip, deflate",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            data = gzip.decompress(data)
        return data.decode("utf-8", errors="replace")


def cached_get(url, use_cache=True):
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".json")
    if use_cache and os.path.exists(path):
        try:
            obj = json.load(open(path, encoding="utf-8"))
            if time.time() - obj.get("ts", 0) < CACHE_TTL:
                return obj.get("html", "")
        except Exception:
            pass
    text = http_get(url)
    try:
        json.dump({"ts": time.time(), "url": url, "html": text},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    return text


# ---------------- 解析器 ----------------
class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.title = ""
        self._in_title = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self.skip:
            return
        if self._in_title:
            self.title += data
        else:
            self.parts.append(data)


def page_text_of(html_text):
    p = PageText()
    try:
        p.feed(html_text)
    except Exception:
        pass
    lines = [WS_RE.sub(" ", x).strip() for x in "".join(p.parts).splitlines()]
    lines = [x for x in lines if len(x) >= 2]
    return clean_text(p.title), "\n".join(lines)[:8000]


def parse_bing(html_text):
    out = []
    for block in re.findall(r'<li class="b_algo".*?</li>', html_text, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        url, title = m.group(1), clean_text(m.group(2))
        sm = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        out.append({"source": "bing", "title": title, "url": html.unescape(url),
                    "snippet": clean_text(sm.group(1)) if sm else ""})
    return out


def parse_ddg(html_text):
    out = []
    for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|'
            r'<div[^>]*class="result__snippet"[^>]*>(.*?)</div>)?',
            html_text, re.S):
        url, title, s1, s2 = m.groups()
        url = html.unescape(url)
        if "uddg=" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("uddg")
            if q:
                url = q[0]
        out.append({"source": "duckduckgo", "title": clean_text(title),
                    "url": url, "snippet": clean_text(s1 or s2 or "")})
    return out


def parse_jyeoo(html_text):
    out, seen = [], set()
    for m in re.finditer(
            r'<a[^>]*href="(/(?:math|math2|math3|physics|chemistry|chinese|english)'
            r'/ques/detail/[^"#?]+)"[^>]*>(.*?)</a>', html_text, re.S):
        url = "https://www.jyeoo.com" + m.group(1)
        if url in seen:
            continue
        seen.add(url)
        out.append({"source": "jyeoo", "title": clean_text(m.group(2)) or "菁优网试题",
                    "url": url, "snippet": ""})
    return out


def parse_so(html_text):
    out, seen = [], set()
    blocks = re.findall(r'<li class="res-list".*?</li>', html_text, re.S)
    if not blocks:
        blocks = re.findall(r'<h3[^>]*>.*?</h3>.*?(?:<p[^>]*class="res-desc".*?</p>)?',
                            html_text, re.S)
    for block in blocks:
        a = re.search(r'<h3[^>]*>\s*<a\b([^>]*)>(.*?)</a>', block, re.S)
        if not a:
            continue
        attrs, title = a.group(1), clean_text(a.group(2))
        href = re.search(r'href="([^"]+)"', attrs)
        md = re.search(r'data-mdurl="([^"]+)"', attrs)
        url = html.unescape(md.group(1)) if md else (
            html.unescape(href.group(1)) if href else "")
        if not title or not url or url in seen:
            continue
        seen.add(url)
        desc = re.search(r'<p[^>]*class="res-desc"[^>]*>(.*?)</p>', block, re.S)
        out.append({"source": "so", "title": title, "url": url,
                    "snippet": clean_text(re.sub(r'<span[^>]*>.*?</span>', '',
                                                 desc.group(1), flags=re.S))
                    if desc else ""})
    return out


def parse_sogou(html_text):
    out, seen = [], set()
    for m in re.finditer(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         html_text, re.S):
        url, title = html.unescape(m.group(1)), clean_text(m.group(2))
        if not title or url in seen:
            continue
        if url.startswith("/link"):
            url = "https://www.sogou.com" + url
        elif not url.startswith("http"):
            continue
        seen.add(url)
        out.append({"source": "sogou", "title": title, "url": url, "snippet": ""})
    return out


# ---------------- 检索 ----------------
def search(provider, query, cookie=None):
    q = urllib.parse.quote(query)
    if provider == "bing":
        return parse_bing(cached_get(f"https://www.bing.com/search?q={q}&count=10&setlang=zh-CN"))
    if provider == "duckduckgo":
        return parse_ddg(cached_get(f"https://html.duckduckgo.com/html/?q={q}"))
    if provider == "so":
        return parse_so(cached_get(f"https://www.so.com/s?q={q}"))
    if provider == "sogou":
        return parse_sogou(cached_get(f"https://www.sogou.com/web?query={q}"))
    if provider == "jyeoo":
        url = f"https://www.jyeoo.com/math/ques/search?q={q}"
        html_text = cached_get(url, use_cache=False)
        results = parse_jyeoo(html_text)
        if not results and ("登录" in html_text or "login" in html_text.lower()):
            print("  ⚠ 菁优网可能要求登录：请设置 JYEOO_COOKIE 环境变量后重试")
        return results
    return []


def offline_links(query):
    q = urllib.parse.quote(query)
    return [
        {"source": "offline", "title": "菁优网搜索", "snippet": "",
         "url": f"https://www.jyeoo.com/math/ques/search?q={q}"},
        {"source": "offline", "title": "必应搜索", "snippet": "",
         "url": f"https://www.bing.com/search?q={q}"},
        {"source": "offline", "title": "百度搜索", "snippet": "",
         "url": f"https://www.baidu.com/s?wd={q}"},
    ]


def robots_ok(url):
    try:
        p = urllib.parse.urlparse(url)
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser(description="原题检索")
    ap.add_argument("--questions", help="cut_questions.py 的 questions.json")
    ap.add_argument("--text", help="单条题干（与 --questions 二选一）")
    ap.add_argument("-o", "--out", default="search_out")
    ap.add_argument("--provider", action="append", default=None,
                    choices=["so", "bing", "sogou", "duckduckgo", "jyeoo", "offline"],
                    help="可重复；默认 so + bing + offline")
    ap.add_argument("--limit", type=int, default=5, help="每题保留候选数")
    ap.add_argument("--limit-q", type=int, default=0, help="只查前 N 题（0=全部）")
    ap.add_argument("--fetch-top", type=int, default=0, help="抓取前 N 条候选正文")
    ap.add_argument("--no-robots", action="store_true", help="不检查 robots.txt")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--include-nonquestions", action="store_true",
                    help="连 likely_question=false 的知识条目也检索")
    args = ap.parse_args()
    global CACHE_TTL
    if args.no_cache:
        CACHE_TTL = 0

    providers = args.provider or ["so", "bing", "offline"]
    cookie = os.environ.get("JYEOO_COOKIE", "")

    items = []
    if args.questions:
        qs = json.load(open(args.questions, encoding="utf-8-sig"))
        if not args.include_nonquestions:
            qs = [q for q in qs if q.get("likely_question") is not False]
        if args.limit_q:
            qs = qs[:args.limit_q]
        for q in qs:
            items.append({"qid": q.get("qid"), "qno": q.get("qno"),
                          "local_text": q.get("text", ""),
                          "page": q.get("page")})
    elif args.text:
        items.append({"qid": "Q001", "qno": 1, "local_text": args.text, "page": None})
    else:
        sys.exit("请提供 --questions 或 --text")

    os.makedirs(args.out, exist_ok=True)
    out_items, md = [], ["# 原题检索清单", ""]
    for it in items:
        query = stem_of(it["local_text"])
        if len(query) < 6:
            it["results"] = []
            continue
        it["query"] = query
        md.append(f"## {it.get('qid') or ('第' + str(it['qno']) + '题')}（原题号 {it['qno']}，第{it['page'] or '?'}页）")
        md.append(f"- 题干：{query}")
        found = []
        for p in providers:
            if p == "offline":
                found.extend(offline_links(query))
                continue
            try:
                res = search(p, query, cookie)
            except Exception as e:
                print(f"  [{p}] 检索失败: {e}")
                res = []
            for r in res:
                r["score"] = similarity(query, r.get("title", "") + " " + r.get("snippet", ""))
            found.extend(res)
            time.sleep(DELAY)
        # 去重 + 排序
        uniq, seen = [], set()
        for r in sorted(found, key=lambda x: x.get("score", 0), reverse=True):
            key = r["url"].split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        it["results"] = uniq[:args.limit]

        if args.fetch_top:
            for r in it["results"][:args.fetch_top]:
                if any(x in r["url"] for x in ("so.com/link", "sogou.com/link",
                                               "bing.com/ck/a", "duckduckgo.com/l/")):
                    r["fetch_error"] = "搜索跳转链接，已跳过抓取（改用标题/摘要比对）"
                    continue
                if not robots_ok(r["url"]) and not args.no_robots:
                    r["fetch_error"] = "robots.txt 不允许抓取"
                    continue
                try:
                    title, text = page_text_of(http_get(r["url"]))
                    r["fetched_title"] = title
                    r["fetched_text"] = text
                    r["score"] = max(r.get("score", 0), similarity(query, text[:1200]))
                except Exception as e:
                    r["fetch_error"] = str(e)[:160]
                time.sleep(DELAY)

        for r in it["results"]:
            md.append(f"- [{r['source']}] {r.get('title', '')} "
                      f"（相似度 {r.get('score', 0):.2f}）{r['url']}")
        md.append("")
        out_items.append(it)

    data = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "providers": providers, "items": out_items}
    with open(os.path.join(args.out, "search_results.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "queries.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md)
                + "\n\n> 题目允许改编：与网上原题不同 ≠ 错误；候选只用于参考/找答案，"
                  "最终按本地题重算并用 verify_answer.py 验证。\n")

    n_hit = sum(1 for x in out_items if x["results"])
    print(f"检索完成: {len(out_items)} 题，{n_hit} 题有候选 → "
          f"{os.path.join(args.out, 'search_results.json')}")
    print("请打开 queries.md 或 search_results.json 逐条核对（AI 只把命中当线索）。")


if __name__ == "__main__":
    main()
