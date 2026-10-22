# -*- coding: utf-8 -*-
"""可视化审阅台（单文件 HTML）
=====================================================
把「本地识别 + 原题检索 + 差异定位 + 人工/AI 结论」合成一个可交互页面：
  - 左侧题目列表：状态徽标 / 相似度 / 搜索过滤；
  - 右侧详情：题目小图、识别文本、原题对照（差异高亮）、问题卡、来源链接；
  - 整页定位：页面图上叠加题目框，点击跳转；
  - 复核结果保存在浏览器 localStorage，可一键导出 JSON（交回 AI 继续处理）。

用法:
  python make_review.py --questions 输出/cut/questions.json -o 输出/review.html
  python make_review.py --questions ... --results 结果.json --diff 输出/diff/diff_results.json \\
      --pages 输出/extract/pages -o 输出/review.html
  python make_review.py --data review.json -o review.html     # 已有合并数据

输入约定:
  questions.json   cut_questions.py 输出
  results.json     校对结论（level: error/doubt/hint；可选 verified）
  diff_results.json diff_question.py 输出
  pages/           extract_pdf.py 渲染的 page_XX.png
"""
import argparse
import base64
import html
import io
import json
import os
import re
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LEVEL_ORDER = {"error": 0, "doubt": 1, "hint": 2, "unchecked": 3, "pass": 4}


def esc(s):
    return html.escape(str(s or ""))


def first_int(s):
    m = re.search(r"\d{1,3}", str(s or ""))
    return int(m.group(0)) if m else None


def file_uri(path, max_w=1000, quality=82):
    """图片 → data URI（有 Pillow 时缩图转 JPEG，显著减小 HTML）。"""
    if not path or not os.path.exists(path):
        return ""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f"data:image/{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()


def norm_diff_text(t):
    if not t:
        return ""
    return re.sub(r"\s+", "", t)


PUNCT_MAP = {"（": "(", "）": ")", "，": ",", "、": ",", "：": ":", "；": ";",
             "．": ".", "。": ".", "？": "?", "！": "!", "－": "-", "−": "-",
             "×": "*", "÷": "/", "≤": "<=", "≥": ">=", "≠": "!=", "　": " "}


def normalize_for_diff(s):
    for a, b in PUNCT_MAP.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def build_diff_html(local, original, spans):
    """把 difflib spans 渲染成本地/原题两栏高亮 HTML。

    位置是 diff_question 在**归一化字符串**上算的，这里必须用同一套归一化，
    否则高亮会错位（踩过：a+b 被吃成 a6）。
    """
    a = normalize_for_diff(local)
    b = normalize_for_diff(original)
    left, right = [], []
    ia = ib = 0
    for sp in spans or []:
        pa, pb = sp.get("local_pos", 0), sp.get("original_pos", 0)
        la, lo = sp.get("local", ""), sp.get("original", "")
        if pa > ia:
            left.append(esc(a[ia:pa]))
        if pb > ib:
            right.append(esc(b[ib:pb]))
        op = sp.get("op")
        cls = "num" if sp.get("kind") == "number" else (
            "op" if sp.get("kind") == "operator" else "txt")
        if la:
            left.append(f'<mark class="del {cls}">{esc(la)}</mark>')
        if lo:
            right.append(f'<mark class="ins {cls}">{esc(lo)}</mark>')
        ia, ib = pa + len(la), pb + len(lo)
    left.append(esc(a[ia:]))
    right.append(esc(b[ib:]))
    return "".join(left), "".join(right)


def load_json(path):
    return json.load(open(path, encoding="utf-8-sig")) if path and os.path.exists(path) else None


def merge(args):
    if args.data:
        return load_json(args.data)

    qs = load_json(args.questions) or []
    results = load_json(args.results) or {}
    diff = load_json(args.diff) or {}
    sizes = {}
    if args.pdf and os.path.exists(args.pdf):
        try:
            import pymupdf
            d = pymupdf.open(args.pdf)
            sizes = {i + 1: {"w": p.rect.width, "h": p.rect.height}
                     for i, p in enumerate(d)}
            d.close()
        except Exception:
            sizes = {}

    issues_by_q, global_issues = {}, []
    for it in results.get("issues", []):
        k = first_int(it.get("qno"))
        (issues_by_q.setdefault(k, []) if k else global_issues).append(it)
    verified_q = {first_int(v) for v in results.get("verified", []) if first_int(v)}
    diff_by_q = {first_int(d.get("qno")): d for d in diff.get("items", [])}

    questions = []
    for q in qs:
        qno = q.get("qno")
        issues = issues_by_q.get(qno, [])
        d = diff_by_q.get(qno, {})
        status = "unchecked"
        lv = [i.get("level") for i in issues]
        if "error" in lv:
            status = "error"
        elif "doubt" in lv:
            status = "doubt"
        elif "hint" in lv:
            status = "hint"
        elif qno in verified_q:
            status = "pass"
        local_text = q.get("text", "")
        dl, dr = build_diff_html(d.get("local_norm") or local_text,
                                 d.get("original_norm") or d.get("original_text", ""),
                                 d.get("diff", []))
        crop = q.get("crop", "")
        if crop and not os.path.isabs(crop):
            base = os.path.dirname(os.path.abspath(args.questions)) if args.questions else "."
            crop = os.path.normpath(os.path.join(base, crop))
        questions.append({
            "qno": qno, "page": q.get("page"), "column": q.get("column"),
            "page_w": q.get("page_w") or sizes.get(q.get("page"), {}).get("w"),
            "page_h": q.get("page_h") or sizes.get(q.get("page"), {}).get("h"),
            "dedupe_rect": q.get("rect"), "text": local_text,
            "crop": file_uri(crop) if args.embed else "",
            "issues": issues,
            "diff": {"verdict": d.get("verdict", ""), "similarity": d.get("similarity"),
                     "original_text": d.get("original_text", ""),
                     "source": d.get("source"), "left_html": dl, "right_html": dr,
                     "issues": d.get("issues", [])},
            "status": status,
        })

    pages = []
    if args.pages and os.path.isdir(args.pages):
        for fn in sorted(os.listdir(args.pages)):
            m = re.match(r"page_(\d+)\.png$", fn, re.I)
            if not m:
                continue
            pno = int(m.group(1))
            rects = [{"qno": q["qno"], "rect": q["dedupe_rect"], "status": q["status"],
                      "pw": q.get("page_w"), "ph": q.get("page_h")}
                     for q in questions if q["page"] == pno and q["dedupe_rect"]]
            pages.append({"page": pno, "img": file_uri(os.path.join(args.pages, fn), 1500),
                          "rects": rects})

    out = {
        "title": args.title or results.get("title") or "数学试卷校对审阅台",
        "source": results.get("source") or (args.questions or ""),
        "mode": results.get("mode", ""),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "questions": questions,
        "pages": pages,
        "global_issues": global_issues,
    }
    return out


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f5f6f8;--card:#fff;--fg:#1c2024;--muted:#6b7280;--line:#e5e7eb;
--red:#d32f2f;--redbg:#fdecea;--amber:#b45309;--amberbg:#fff7ed;--blue:#1d4ed8;--bluebg:#eff6ff;
--green:#15803d;--greenbg:#ecfdf5;--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#111418;--card:#1a1f25;--fg:#e5e7eb;--muted:#9aa4b2;
--line:#2b333d;--redbg:#3a1d1d;--amberbg:#3a2a17;--bluebg:#182538;--greenbg:#14301f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:20;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px}
.hrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0 12px 0 0;font-weight:650}
.sub{color:var(--muted);font-size:12px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:999px;
padding:4px 10px;font-size:12px;cursor:pointer}
.chip.active{background:var(--accent);border-color:var(--accent);color:#fff}
.chip .n{opacity:.8;margin-left:4px}
#search{margin-left:auto;min-width:200px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--fg)}
main{display:grid;grid-template-columns:360px 1fr;gap:14px;padding:14px;max-width:1600px;margin:0 auto}
@media(max-width:900px){main{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
#list{max-height:calc(100vh - 120px);overflow:auto}
.qitem{padding:10px 12px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;gap:10px}
.qitem:hover{background:var(--bg)}
.qitem.sel{background:color-mix(in srgb,var(--accent) 12%,transparent);border-left:3px solid var(--accent)}
.qno{font-weight:700;min-width:34px}
.qitem .txt{color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{font-size:11px;padding:1px 7px;border-radius:999px;white-space:nowrap;font-weight:600}
.b-error{background:var(--redbg);color:var(--red)}
.b-doubt{background:var(--amberbg);color:var(--amber)}
.b-hint{background:var(--bluebg);color:var(--blue)}
.b-pass{background:var(--greenbg);color:var(--green)}
.b-unchecked{background:var(--bg);color:var(--muted)}
#detail{padding:16px;min-height:300px}
.qhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.qhead h2{font-size:20px;margin:0}
.tabs{display:flex;gap:6px;margin-left:auto}
.tabs button{border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:8px;padding:5px 10px;cursor:pointer}
.tabs button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.grid{display:grid;grid-template-columns:minmax(260px,44%) 1fr;gap:14px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.crop{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:zoom-in}
.textbox{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;
font-family:ui-monospace,Consolas,"Microsoft YaHei",monospace;font-size:13px}
.diff{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:760px){.diff{grid-template-columns:1fr}}
.diff .col{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:13px}
.diff .col h4{margin:0 0 6px;font-size:12px;color:var(--muted);font-weight:600}
mark.del{border-radius:3px;padding:0 1px}
mark.ins{border-radius:3px;padding:0 1px}
mark.num.del{background:#ffd7d5;color:#a40000}
mark.num.ins{background:#c9f7d4;color:#00601f}
mark.op.del{background:#ffe8b3;color:#7a4b00}
mark.op.ins{background:#d6e9ff;color:#003c8f}
mark.txt.del{background:#ffe1ea;color:#8f003a}
mark.txt.ins{background:#e2d9ff;color:#3b0b8f}
.issue{border:1px solid var(--line);border-left:4px solid var(--muted);border-radius:8px;padding:10px 12px;margin:8px 0;background:var(--card)}
.issue.error{border-left-color:var(--red);background:var(--redbg)}
.issue.doubt{border-left-color:var(--amber);background:var(--amberbg)}
.issue.hint{border-left-color:var(--blue);background:var(--bluebg)}
.issue b{font-size:13px}
.issue p{margin:4px 0;font-size:13px}
.meta{color:var(--muted);font-size:12px}
a{color:var(--accent)}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.toolbar button,.toolbar a.btn{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;
padding:6px 10px;cursor:pointer;text-decoration:none;font-size:13px}
.toolbar .save{background:var(--accent);color:#fff;border-color:var(--accent)}
textarea{width:100%;min-height:64px;margin-top:8px;padding:8px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--fg);font:13px/1.5 inherit;resize:vertical}
#pageMode{display:none;padding:16px}
.pagewrap{position:relative;max-width:900px;margin:0 auto 22px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.pagewrap img{width:100%;display:block}
.box{position:absolute;border:1.5px solid var(--accent);background:color-mix(in srgb,var(--accent) 8%,transparent);
cursor:pointer;border-radius:2px}
.box.error{border-color:var(--red);background:color-mix(in srgb,var(--red) 10%,transparent)}
.box.doubt{border-color:var(--amber);background:color-mix(in srgb,var(--amber) 10%,transparent)}
.box.hint{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 10%,transparent)}
.box.pass{border-color:var(--green);background:color-mix(in srgb,var(--green) 10%,transparent)}
.box span{position:absolute;left:0;top:-18px;font-size:11px;background:var(--card);padding:0 4px;border-radius:3px}
.empty{color:var(--muted);padding:30px;text-align:center}
.statbar{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:6px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.82);display:none;align-items:center;justify-content:center;z-index:99}
#lightbox img{max-width:94vw;max-height:92vh;background:#fff}
#global{padding:10px 12px;border-bottom:1px solid var(--line)}
</style>
</head>
<body>
<header>
  <div class="hrow">
    <h1 id="title"></h1>
    <span class="sub" id="sub"></span>
    <input id="search" placeholder="搜索题号 / 题干（按 / 聚焦）">
  </div>
  <div class="hrow" style="margin-top:8px">
    <div class="chips" id="chips"></div>
    <div class="tabs">
      <button id="tabList" class="on">题目列表</button>
      <button id="tabPage">整页定位</button>
    </div>
  </div>
  <div class="statbar" id="stats"></div>
</header>
<main>
  <section class="panel">
    <div id="global"></div>
    <div id="list"></div>
  </section>
  <section class="panel">
    <div id="detail"><div class="empty">从左栏选择一道题</div></div>
    <div id="pageMode"></div>
  </section>
</main>
<div id="lightbox"><img id="lightimg"></div>

<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const STORE_KEY = 'mpp-review:' + (DATA.source || '') + ':' + (DATA.title || '');
const overrides = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
const state = {filter:'all', q:null, mode:'list', query:''};
const LEVEL = {error:['错误','b-error'],doubt:['存疑','b-doubt'],hint:['提示','b-hint'],
               pass:['已核验','b-pass'],unchecked:['未核对','b-unchecked']};

function statusOf(q){ return (overrides[q.qno] && overrides[q.qno].status) || q.status; }
function noteOf(q){ return (overrides[q.qno] && overrides[q.qno].note) || ''; }
function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }
function badge(st){ const [t,c]=LEVEL[st]||LEVEL.unchecked; return `<span class="badge ${c}">${t}</span>`; }
function counts(){
  const c={error:0,doubt:0,hint:0,pass:0,unchecked:0};
  DATA.questions.forEach(q=>c[statusOf(q)]++); return c;
}
function filtered(){
  return DATA.questions.filter(q=>{
    const st=statusOf(q);
    if(state.filter!=='all' && st!==state.filter) return false;
    if(state.query){ const s=state.query.toLowerCase();
      return (String(q.qno).includes(s)) || (q.text||'').toLowerCase().includes(s) ||
             (q.diff.original_text||'').toLowerCase().includes(s);
    }
    return true;
  });
}
function renderChips(){
  const c=counts(), defs=[['all','全部',DATA.questions.length],['error','错误',c.error],
    ['doubt','存疑',c.doubt],['hint','提示',c.hint],['pass','已核验',c.pass],['unchecked','未核对',c.unchecked]];
  document.getElementById('chips').innerHTML=defs.map(([k,t,n])=>
    `<button class="chip ${state.filter===k?'active':''}" data-f="${k}">${t}<span class="n">${n}</span></button>`).join('');
  document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{state.filter=b.dataset.f;render();});
}
function renderStats(){
  const c=counts();
  document.getElementById('stats').innerHTML =
    `<span><i class="dot" style="background:var(--red)"></i>错误 ${c.error}</span>`+
    `<span><i class="dot" style="background:var(--amber)"></i>存疑 ${c.doubt}</span>`+
    `<span><i class="dot" style="background:var(--blue)"></i>提示 ${c.hint}</span>`+
    `<span><i class="dot" style="background:var(--green)"></i>已核验 ${c.pass}</span>`+
    `<span><i class="dot" style="background:var(--muted)"></i>未核对 ${c.unchecked}</span>`;
}
function renderList(){
  const items=filtered();
  document.getElementById('list').innerHTML = items.length ? items.map(q=>{
    const st=statusOf(q), sim=q.diff.similarity;
    return `<div class="qitem ${state.q===q.qno?'sel':''}" data-q="${q.qno}">
      <div class="qno">${q.qno}</div>
      <div style="flex:1;min-width:0">
        <div style="display:flex;gap:6px;align-items:center">${badge(st)}
          <span class="meta">第${q.page}页${q.column===1?' · 右栏':''}${sim!=null?` · 相似 ${Number(sim).toFixed(2)}`:''}</span></div>
        <div class="txt">${esc(q.text||'')||'<i>无文本</i>'}</div>
      </div></div>`;
  }).join('') : '<div class="empty">没有匹配的题目</div>';
  document.querySelectorAll('.qitem').forEach(el=>el.onclick=()=>select(Number(el.dataset.q)));
}
function renderGlobal(){
  const g=DATA.global_issues||[];
  document.getElementById('global').innerHTML = g.length ? `<div class="meta" style="margin-bottom:6px">全卷/版面问题（${g.length}）</div>`+
    g.map(i=>`<div class="issue ${esc(i.level||'hint')}" style="margin:6px 0">
      <b>${esc(i.type||'问题')}</b> <span class="meta">第${esc(i.page||'?')}页</span>
      <p>${esc(i.desc||'')}</p>${i.correct?`<p><b>建议：</b>${esc(i.correct)}</p>`:''}</div>`).join('') : '';
}
function issueHtml(i){
  return `<div class="issue ${esc(i.level||'hint')}">
    <b>${esc(i.type||'问题')}</b>
    ${i.qno?`<span class="meta"> · ${esc(i.qno)}</span>`:''}
    <p>${esc(i.desc||'')}</p>
    ${i.correct?`<p><b>正确答案 / 建议：</b>${esc(i.correct)}</p>`:''}
    ${i.evidence?`<p class="meta">依据：${esc(i.evidence)}</p>`:''}
  </div>`;
}
function renderDetail(){
  const box=document.getElementById('detail');
  const q=DATA.questions.find(x=>x.qno===state.q);
  if(!q){ box.innerHTML='<div class="empty">从左栏选择一道题（↑/↓ 或 j/k 切换）</div>'; return; }
  const st=statusOf(q);
  const diff=q.diff||{}, src=diff.source||{};
  const hasDiff=!!(diff.right_html);
  box.innerHTML=`
    <div class="qhead"><h2>第 ${q.qno} 题</h2>${badge(st)}
      <span class="meta">第 ${q.page} 页${q.column===1?' · 右栏':''}</span>
      <div class="tabs">
        <button id="btnPrev">↑ 上一题</button><button id="btnNext">下一题 ↓</button>
      </div>
    </div>
    <div class="grid">
      <div>
        ${q.crop?`<img class="crop" id="cropImg" src="${q.crop}" alt="题目小图">`:'<div class="empty">无题目小图</div>'}
      </div>
      <div>
        <h4 style="margin:0 0 6px;font-size:12px;color:var(--muted)">识别文本（本地）</h4>
        <div class="textbox">${esc(q.text||'（空）')}</div>
        ${q.issues&&q.issues.length?`<h4 style="margin:12px 0 4px;font-size:12px;color:var(--muted)">批注问题</h4>
          ${q.issues.map(issueHtml).join('')}`:''}
        ${diff.issues&&diff.issues.length?`<h4 style="margin:12px 0 4px;font-size:12px;color:var(--muted)">与原题的差异线索</h4>
          ${diff.issues.map(i=>`<div class="issue ${i.level==='high'?'error':i.level==='medium'?'doubt':'hint'}">
            <b>${esc(i.type)}</b><p>${esc(i.desc)}</p></div>`).join('')}`:''}
      </div>
    </div>
    ${hasDiff?`<h4 style="margin:16px 0 6px;font-size:12px;color:var(--muted)">
        原题对照 · ${esc(diff.verdict||'')} ${diff.similarity!=null?`（相似度 ${Number(diff.similarity).toFixed(2)}）`:''}</h4>
      <div class="diff">
        <div class="col"><h4>本地（红=多/改）</h4>${diff.left_html}</div>
        <div class="col"><h4>原题（绿=原题有）</h4>${diff.right_html}</div>
      </div>
      ${src.url?`<p class="meta">来源：<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.title||src.url)}</a>
        ${src.provider?` · ${esc(src.provider)}`:''}</p>`:''}
    `:`<p class="meta" style="margin-top:14px">未检索到原题或尚未生成差异对照。
       可运行 <code>search_original.py</code> + <code>diff_question.py</code> 后重新生成本页。</p>`}
    <div class="toolbar">
      <span class="meta" style="align-self:center">人工复核：</span>
      <button data-set="error">标为错误</button>
      <button data-set="doubt">标为存疑</button>
      <button data-set="hint">标为提示</button>
      <button data-set="pass">标为无误</button>
      <button class="save" id="saveNote">保存备注</button>
      <button id="exportBtn">导出复核 JSON</button>
    </div>
    <textarea id="note" placeholder="写复核备注：错在哪、依据、最终结论…">${esc(noteOf(q))}</textarea>`;
  document.querySelectorAll('[data-set]').forEach(b=>b.onclick=()=>{
    overrides[q.qno]=overrides[q.qno]||{}; overrides[q.qno].status=b.dataset.set;
    overrides[q.qno].note=document.getElementById('note').value;
    persist(); render();
  });
  document.getElementById('saveNote').onclick=()=>{
    overrides[q.qno]=overrides[q.qno]||{}; overrides[q.qno].note=document.getElementById('note').value;
    persist(); flash('备注已保存');
  };
  document.getElementById('exportBtn').onclick=exportJson;
  document.getElementById('btnPrev').onclick=()=>step(-1);
  document.getElementById('btnNext').onclick=()=>step(1);
  const img=document.getElementById('cropImg');
  if(img) img.onclick=()=>{document.getElementById('lightimg').src=img.src;
    document.getElementById('lightbox').style.display='flex';};
}
function step(d){
  const items=filtered(); if(!items.length) return;
  let i=items.findIndex(x=>x.qno===state.q);
  i=(i+d+items.length)%items.length; select(items[i].qno);
}
function select(qno){
  state.q=qno; state.mode='list';
  document.getElementById('tabList').classList.add('on');
  document.getElementById('tabPage').classList.remove('on');
  document.getElementById('detail').style.display='block';
  document.getElementById('pageMode').style.display='none';
  renderList(); renderDetail();
  const el=document.querySelector('.qitem.sel'); if(el) el.scrollIntoView({block:'nearest'});
  history.replaceState(null,'','#q='+qno);
}
function renderPages(){
  const box=document.getElementById('pageMode');
  if(!DATA.pages||!DATA.pages.length){ box.innerHTML='<div class="empty">没有整页图：运行 extract_pdf.py（去掉 --no-pages）后重新生成。</div>'; return; }
  box.innerHTML=DATA.pages.map(p=>{
    const boxes=(p.rects||[]).map(r=>{
      if(!r.rect) return '';
      const [x0,y0,x1,y1]=r.rect;
      const PW=r.pw||595, PH=r.ph||842;
      const L=x0/PW*100,T=y0/PH*100,W=(x1-x0)/PW*100,H=(y1-y0)/PH*100;
      return `<div class="box ${esc(r.status||'')}" data-q="${r.qno}" style="left:${L}%;top:${T}%;width:${W}%;height:${H}%">
        <span>${r.qno}</span></div>`;
    }).join('');
    return `<div class="pagewrap"><img src="${p.img}" alt="第${p.page}页">${boxes}</div>`;
  }).join('');
  box.querySelectorAll('.box').forEach(b=>b.onclick=()=>{
    select(Number(b.dataset.q));
  });
}
function render(){
  document.getElementById('title').textContent=DATA.title;
  document.getElementById('sub').textContent=[DATA.source,DATA.mode,DATA.generated].filter(Boolean).join(' · ');
  renderChips(); renderStats(); renderGlobal(); renderList(); renderDetail();
}
function persist(){ localStorage.setItem(STORE_KEY,JSON.stringify(overrides)); }
function flash(msg){
  const d=document.createElement('div');
  d.textContent=msg; d.style.cssText='position:fixed;right:18px;bottom:18px;background:var(--accent);color:#fff;padding:8px 14px;border-radius:8px;z-index:100';
  document.body.appendChild(d); setTimeout(()=>d.remove(),1600);
}
function exportJson(){
  const out={title:DATA.title,source:DATA.source,exported:new Date().toISOString(),
    questions:DATA.questions.map(q=>({qno:q.qno,page:q.page,auto_status:q.status,
      status:statusOf(q),note:noteOf(q),issues:q.issues,
      diff:{verdict:q.diff.verdict,similarity:q.diff.similarity,issues:q.diff.issues,
            source:q.diff.source}}))};
  const blob=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='review_results.json'; a.click(); URL.revokeObjectURL(a.href);
}
document.getElementById('search').oninput=e=>{state.query=e.target.value.trim();renderList();};
document.getElementById('tabList').onclick=()=>{state.mode='list';
  document.getElementById('detail').style.display='block';
  document.getElementById('pageMode').style.display='none';
  document.getElementById('tabList').classList.add('on');
  document.getElementById('tabPage').classList.remove('on');};
document.getElementById('tabPage').onclick=()=>{state.mode='page';
  document.getElementById('detail').style.display='none';
  document.getElementById('pageMode').style.display='block';
  document.getElementById('tabPage').classList.add('on');
  document.getElementById('tabList').classList.remove('on');
  renderPages();};
document.getElementById('lightbox').onclick=()=>document.getElementById('lightbox').style.display='none';
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
  if(e.key==='/'){e.preventDefault();document.getElementById('search').focus();}
  if(['j','ArrowDown'].includes(e.key)){e.preventDefault();step(1);}
  if(['k','ArrowUp'].includes(e.key)){e.preventDefault();step(-1);}
  if(e.key==='1')  setKey('error');
  if(e.key==='2')  setKey('doubt');
  if(e.key==='3')  setKey('hint');
  if(e.key==='4')  setKey('pass');
});
function setKey(st){
  const q=DATA.questions.find(x=>x.qno===state.q); if(!q) return;
  overrides[q.qno]=overrides[q.qno]||{}; overrides[q.qno].status=st;
  overrides[q.qno].note=noteOf(q); persist(); render();
}
const hash=new URLSearchParams(location.hash.replace('#',''));
if(hash.get('q')) state.q=Number(hash.get('q'));
render();
if(state.q) select(state.q);
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="生成可视化审阅台（单文件 HTML）")
    ap.add_argument("--questions", help="questions.json")
    ap.add_argument("--results", help="results.json（人工/AI 结论）")
    ap.add_argument("--diff", help="diff_results.json")
    ap.add_argument("--pages", help="extract_pdf.py 的 pages 目录")
    ap.add_argument("--pdf", help="原 PDF（用于读取页面尺寸，修正整页框定位）")
    ap.add_argument("--data", help="已合并的 review.json（跳过其它输入）")
    ap.add_argument("-o", "--out", default="review.html")
    ap.add_argument("--title", default=None)
    ap.add_argument("--embed-images", default=True, action="store_true",
                    help="题目小图 base64 内嵌（默认开）")
    ap.add_argument("--no-images", dest="embed_images", action="store_false")
    args = ap.parse_args()

    if not args.questions and not args.data:
        sys.exit("请提供 --questions 或 --data")

    args.embed = args.embed_images
    data = merge(args)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = TEMPLATE.replace("__TITLE__", esc(data.get("title", "校对审阅台"))) \
                  .replace("__DATA__", payload)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(out)
    size = os.path.getsize(args.out) / 1024 / 1024
    print(f"审阅台: {os.path.abspath(args.out)}（{size:.1f} MB，{len(data['questions'])} 题）")
    print("用浏览器打开即可；复核结果可导出 JSON 再交给 AI。")


if __name__ == "__main__":
    main()
