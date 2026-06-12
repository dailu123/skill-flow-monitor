#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把双库分析进度渲染成 skillflow-monitor 的两个 JSON：

  pipeline.json  ← --view 决定内容：
      overview  双分支总览（MCA分支 + HUB分支 → 对比 → 业务报告）
      mca / hub 该仓库的目录地图（节点=目录，颜色=分析状态）
  lineage.json   ← 永远由 evidence/capabilities.csv 生成：
      业务能力对齐图（两边模块 → 业务能力 → 对比报告；单边缺失=红色）

用法（Windows）：
  python code-analysis-kit\\render_status.py --out-dir skillflow-monitor\\public\\status
  python code-analysis-kit\\render_status.py --out-dir ... --view mca
  python code-analysis-kit\\render_status.py --out-dir ... --watch 2      # 实时刷新
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime

KIT = os.path.dirname(os.path.abspath(__file__))
STATUS_MAP = {"TODO": "pending", "IN_PROGRESS": "running", "DONE": "done",
              "ERROR": "error", "SKIP": "skipped"}
PCT = {"pending": 0, "running": 50, "done": 100, "error": 0, "skipped": 0}
REPO_CHIP = {"mca": "sql", "hub": "rpg"}  # 节点彩色小标签：蓝=MCA(Java)，紫=HUB(AS400)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def nid(prefix, s):
    return prefix + "_" + re.sub(r"[^0-9A-Za-z]", "_", s)


def parse_progress(name):
    """读 work/<name>/PROGRESS.md，返回单元列表 [{id,dir,count,status,...}]。"""
    path = os.path.join(KIT, "work", name, "PROGRESS.md")
    units = []
    if not os.path.exists(path):
        return units
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.lstrip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4 or cells[0].upper() == "ID" or set(cells[0]) <= set("-: "):
                continue
            status = STATUS_MAP.get(cells[3].upper().replace(" ", "_"))
            if status is None:
                continue
            # 单元名可能带 “ [块k/n]” 后缀，目录取前半段
            d = re.sub(r"\s*\[块\d+/\d+\]\s*$", "", cells[1]).lstrip("./")
            units.append({
                "id": cells[0], "dir": d, "label": cells[1],
                "count": int(cells[2]) if cells[2].isdigit() else 0,
                "status": status,
                "filelist": cells[4] if len(cells) > 4 else "",
                "note": cells[5] if len(cells) > 5 else "",
                "summary": cells[6] if len(cells) > 6 else "",
            })
    return units


def report_exists(fn):
    return os.path.exists(os.path.join(KIT, "reports", fn))


def cap_rows():
    """读 evidence/capabilities.csv（容忍 Excel 的 BOM）。"""
    path = os.path.join(KIT, "evidence", "capabilities.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("capability") or "").strip()]


# ---------- 总览视图 ----------
def phase_node(pid, name, status, progress, detail):
    return {"id": pid, "name": name, "type": "skill", "status": status,
            "progress": progress, "detail": detail}


def repo_phase(name, cn):
    """一个仓库分支的三个阶段节点。"""
    units = parse_progress(name)
    total = len(units)
    skipped = sum(1 for u in units if u["status"] == "skipped")
    eff = total - skipped  # SKIP（预分类跳过的沉淀物）不计入分析任务
    done = sum(1 for u in units if u["status"] == "done")
    running = sum(1 for u in units if u["status"] == "running")

    map_st = "done" if total else "pending"
    if eff and done >= eff:
        ana_st, ana_pct = "done", 100
    elif running or done:
        ana_st, ana_pct = "running", round(100 * done / eff) if eff else 0
    else:
        ana_st, ana_pct = "pending", 0
    # 阶段A2：调用链穿刺（evidence/<name>/traces/）
    tr_dir = os.path.join(KIT, "evidence", name, "traces")
    n_tr = len([f for f in os.listdir(tr_dir)
                if f.lower().endswith(".md") and not f.startswith("_")]) if os.path.isdir(tr_dir) else 0
    idx = os.path.join(tr_dir, "_INDEX.md")
    idx_complete = False
    if os.path.exists(idx):
        with open(idx, encoding="utf-8") as fh:
            idx_complete = "STATUS: COMPLETE" in fh.read()
    if idx_complete and n_tr:
        tr_st, tr_pct = "done", 100
    elif n_tr or ana_st == "done":
        tr_st, tr_pct = "running", min(95, n_tr * 10)
    else:
        tr_st, tr_pct = "pending", 0

    arch_fn = f"ARCH-{name}.md"
    arch_st = "done" if report_exists(arch_fn) else ("running" if tr_st == "done" else "pending")

    return [
        phase_node(f"{name}-map", f"{cn} 地图扫描", map_st, PCT[map_st],
                   f"{total} 个分析单元" if total else "待 bootstrap"),
        phase_node(f"{name}-analyze", f"{cn} 模块分析", ana_st, ana_pct,
                   f"{done}/{eff} 单元完成" + (f"（另 {skipped} 个已跳过）" if skipped else "")),
        phase_node(f"{name}-trace", f"{cn} 调用链穿刺", tr_st, tr_pct,
                   f"{n_tr} 条业务链已穿刺"),
        phase_node(f"{name}-arch", f"{cn} 架构汇总", arch_st, PCT[arch_st],
                   f"reports/{arch_fn}"),
    ], [
        {"from": f"{name}-map", "to": f"{name}-analyze"},
        {"from": f"{name}-analyze", "to": f"{name}-trace"},
        {"from": f"{name}-trace", "to": f"{name}-arch"},
    ]


def build_overview():
    n_m, e_m = repo_phase("mca", "MCA(Java)")
    n_h, e_h = repo_phase("hub", "HUB(AS400)")
    caps = cap_rows()
    both_arch = report_exists("ARCH-mca.md") and report_exists("ARCH-hub.md")
    cmp_st = "done" if report_exists("COMPARE.md") else ("running" if both_arch else "pending")
    biz_st = "done" if report_exists("BUSINESS.md") else ("running" if cmp_st == "done" else "pending")
    nodes = n_m + n_h + [
        phase_node("compare", "交叉对比", cmp_st, PCT[cmp_st],
                   f"{len(caps)} 项业务能力已对齐"),
        phase_node("business", "业务视角报告", biz_st, PCT[biz_st], "reports/BUSINESS.md"),
    ]
    edges = e_m + e_h + [
        {"from": "mca-arch", "to": "compare"},
        {"from": "hub-arch", "to": "compare"},
        {"from": "compare", "to": "business"},
    ]
    return {"title": "MCA(Java) vs HUB(AS400) 双库对比分析",
            "skills": nodes, "edges": edges, "updatedAt": now()}


# ---------- 依赖连线：SYMBOLS 的 import/CALL 图 + AI 验证的 relations.csv ----------
def dir_of(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else "."


def load_symbols(name):
    path = os.path.join(KIT, "work", name, "SYMBOLS.txt")
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 3:
                    out.append(parts)
    return out


def dep_edges(name, dirset):
    """返回 {(from_dir, to_dir)}，两端都收敛到任务队列里存在的目录。"""
    syms = load_symbols(name)
    defs = {}  # 类名/程序名 -> 定义它的目录集合
    for f, k, sym in syms:
        if k == "type":
            defs.setdefault(sym, set()).add(dir_of(f))
        elif k == "program":
            defs.setdefault(sym.upper(), set()).add(dir_of(f))

    raw = set()
    for f, k, sym in syms:
        a = dir_of(f)
        if k == "import":  # Java：import 的类在哪个目录定义，且包路径后缀要对得上（防同名误连）
            cls = sym.rsplit(".", 1)[-1]
            pkg = sym.rsplit(".", 1)[0].replace(".", "/") if "." in sym else ""
            for b in defs.get(cls, ()):
                if not pkg or b.endswith(pkg):
                    raw.add((a, b))
        elif k == "call":  # RPG/CL：CALL 的程序在哪个目录定义
            for b in defs.get(sym.upper(), ()):
                raw.add((a, b))

    # AI 分析时验证/发现的关系（共享表、MQ、文件接口等正则看不出来的）
    rp = os.path.join(KIT, "evidence", name, "relations.csv")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                a = (r.get("from") or "").strip().lstrip("./")
                b = (r.get("to") or "").strip().lstrip("./")
                if a and b:
                    raw.add((a, b))

    def climb(d):  # 收敛到队列中存在的目录（小目录可能已被归并）
        while d and d not in dirset:
            d = d.rsplit("/", 1)[0] if "/" in d else None
        return d

    out = set()
    for a, b in raw:
        ca, cb = climb(a), climb(b)
        if ca and cb and ca != cb:
            out.add((ca, cb))
    return out


# ---------- 单仓库目录视图 ----------
def build_repo_view(name):
    units = parse_progress(name)
    by_dir = {}
    for u in units:
        by_dir.setdefault(u["dir"], []).append(u)

    chip = REPO_CHIP.get(name, "file")
    nodes, dirset = [], set(by_dir)
    for d, us in sorted(by_dir.items()):
        sts = [u["status"] for u in us]
        if all(s == "skipped" for s in sts):
            st = "skipped"
        elif all(s in ("done", "skipped") for s in sts):
            st = "done"
        elif "error" in sts:
            st = "error"
        elif any(s in ("running", "done") for s in sts):
            st = "running"
        else:
            st = "pending"
        eff = [s for s in sts if s != "skipped"] or sts
        pct = round(sum(PCT[s] for s in eff) / len(eff))
        summary = next((u["summary"] for u in us if u["summary"]), "")
        n_files = sum(u["count"] for u in us)
        detail = summary or (f"{n_files} 文件 · {len(us)} 块" if len(us) > 1 else f"{n_files} 个源码文件")
        nodes.append({"id": nid("d", d), "name": d.split("/")[-1] if d != "." else "(root)",
                      "type": chip, "status": st, "progress": pct, "detail": detail})

    deps = dep_edges(name, dirset)
    edges = [{"from": nid("d", a), "to": nid("d", b)} for a, b in sorted(deps)]
    linked = {a for a, _ in deps} | {b for _, b in deps}
    for d in by_dir:  # 没有任何依赖线的节点，用目录树边兜底，避免悬空
        if d in linked:
            continue
        parts = d.split("/")
        for i in range(len(parts) - 1, 0, -1):
            anc = "/".join(parts[:i])
            if anc in dirset:
                edges.append({"from": nid("d", anc), "to": nid("d", d)})
                break
    title_cn = {"mca": "MCA(Java) 代码地图", "hub": "HUB(AS400) 代码地图"}.get(name, f"{name} 代码地图")
    return {"title": title_cn, "skills": nodes, "edges": edges, "updatedAt": now()}


# ---------- 业务能力对齐图（lineage.json） ----------
PARITY_STATUS = {"both": "done", "mca-only": "error", "hub-only": "error",
                 "uncertain": "pending", "": "pending"}


def build_lineage(mode="gaps"):
    """mode=gaps 只画 parity!=both 的缺口项（图的正确用法：少量重点）；mode=all 全画。"""
    rows = cap_rows()
    if mode == "gaps":
        rows = [r for r in rows if (r.get("parity") or "").strip().lower() != "both"]
    if not rows:
        return None
    overflow = max(0, len(rows) - 60)
    rows = rows[:60]  # 图只能承载这么多；全量看 matrix.html
    nodes, edges, seen = [], [], set()
    known_dirs = {u["dir"] for u in parse_progress("mca")} | {u["dir"] for u in parse_progress("hub")}

    cmp_done = report_exists("COMPARE.md")
    nodes.append({"id": "REPORT", "label": "对比报告", "type": "table",
                  "status": "done" if cmp_done else "pending",
                  "progress": 100 if cmp_done else 0,
                  "detail": f"另有 {overflow} 项见 matrix.html" if overflow else "reports/COMPARE.md"})

    for r in rows:
        cap = r["capability"].strip()
        parity = (r.get("parity") or "").strip().lower()
        cid = nid("cap", cap)
        st = PARITY_STATUS.get(parity, "pending")
        detail = (r.get("note") or "").strip() or {"both": "两边都有", "mca-only": "仅 MCA 有",
                                                   "hub-only": "仅 HUB 有"}.get(parity, "未确认")
        nodes.append({"id": cid, "label": cap, "type": "table", "status": st,
                      "progress": PCT[st], "detail": f"[{r.get('domain','')}] {detail}".strip()})
        edges.append({"from": cid, "to": "REPORT"})

        for side, col, ev_col in (("mca", "mca_modules", "mca_evidence"),
                                  ("hub", "hub_modules", "hub_evidence")):
            for mod in (r.get(col) or "").split(";"):
                mod = mod.strip().lstrip("./")
                if not mod:
                    continue
                mid = nid(side, mod)
                if mid not in seen:
                    seen.add(mid)
                    warn = "" if (mod in known_dirs or not known_dirs) else " ⚠未在队列中"
                    nodes.append({"id": mid, "label": f"{side.upper()}:{mod.split('/')[-1]}",
                                  "type": REPO_CHIP[side], "status": "done", "progress": 100,
                                  "detail": (r.get(ev_col) or mod)[:80] + warn})
                    if warn:
                        print(f"  [印证警告] 能力「{cap}」引用的 {side} 模块不在任务队列里: {mod}")
                edges.append({"from": mid, "to": cid})

    return {"target": "REPORT", "nodes": nodes, "edges": edges, "updatedAt": now()}


PARITY_CN = {"both": ("两边都有", "#1e8e3e"), "mca-only": ("仅 MCA", "#d93025"),
             "hub-only": ("仅 HUB", "#d93025"), "uncertain": ("未确认", "#9aa0a6")}


def build_matrix_html():
    """能力/映射对齐矩阵：数据嵌 JSON，DOM 只渲染过滤后前 400 行 → 上万行不卡。"""
    rows = cap_rows()
    cols = ("domain", "capability", "parity", "mca_modules", "mca_evidence",
            "hub_modules", "hub_evidence", "note")
    data = [{k: (r.get(k) or "").strip() for k in cols} for r in rows]
    data.sort(key=lambda r: (r["domain"], r["capability"]))
    cnt = {}
    for r in data:
        cnt[r["parity"].lower() or "uncertain"] = cnt.get(r["parity"].lower() or "uncertain", 0) + 1
    summary = " · ".join(f"{PARITY_CN.get(k, (k,))[0]} {v}" for k, v in sorted(cnt.items()))
    domains = sorted({r["domain"] for r in data if r["domain"]})
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    dom_opts = "".join(f'<option>{d}</option>' for d in domains)
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>业务能力对齐矩阵</title><style>
body{font:14px/1.5 -apple-system,'Segoe UI',sans-serif;margin:24px;color:#202124}
h1{font-size:18px} .sub{color:#5f6368;margin-bottom:12px}
.bar{display:flex;gap:8px;margin-bottom:12px;align-items:center}
input,select{padding:6px 10px;border:1px solid #dadce0;border-radius:6px}
input{width:260px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #e0e0e0;padding:5px 9px;text-align:left;vertical-align:top}
th{background:#f1f3f4;position:sticky;top:0}
tr.mca-only td,tr.hub-only td{background:#fce8e6} tr.both td{background:#e6f4ea}
.badge{color:#fff;border-radius:10px;padding:1px 8px;font-size:12px;white-space:nowrap}
.ev{color:#5f6368;font-size:12px} #more{color:#5f6368;padding:10px}
</style></head><body>
<h1>业务能力对齐矩阵（MCA ↔ HUB）</h1>
<div class="sub">__SUMMARY__　|　生成于 __NOW__　|　数据源 evidence/capabilities.csv（F5 刷新）</div>
<div class="bar">
<input id="q" placeholder="搜索：能力 / 模块 / 证据...">
<select id="dom"><option value="">全部业务域</option>__DOMS__</select>
<select id="par"><option value="">全部状态</option><option>both</option><option>mca-only</option>
<option>hub-only</option><option>uncertain</option></select>
<span id="n"></span></div>
<table><thead><tr><th>业务域</th><th>能力</th><th>对齐</th><th>MCA(Java)</th><th>HUB(AS400)</th>
<th>备注</th></tr></thead><tbody id="tb"></tbody></table><div id="more"></div>
<script>
var DATA=__DATA__,CAP=400,t=null;
var COLOR={both:'#1e8e3e','mca-only':'#d93025','hub-only':'#d93025',uncertain:'#9aa0a6'};
var LABEL={both:'两边都有','mca-only':'仅 MCA','hub-only':'仅 HUB',uncertain:'未确认'};
function esc(x){return x.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function render(){
  var q=document.getElementById('q').value.toLowerCase(),
      d=document.getElementById('dom').value,p=document.getElementById('par').value;
  var hit=DATA.filter(function(r){
    if(d&&r.domain!==d)return false;
    var pr=(r.parity||'uncertain').toLowerCase();
    if(p&&pr!==p)return false;
    if(q&&JSON.stringify(r).toLowerCase().indexOf(q)<0)return false;
    return true});
  var rows=hit.slice(0,CAP).map(function(r){
    var pr=(r.parity||'uncertain').toLowerCase();
    return '<tr class="'+pr+'"><td>'+esc(r.domain)+'</td><td><b>'+esc(r.capability)+
      '</b></td><td><span class="badge" style="background:'+(COLOR[pr]||'#9aa0a6')+'">'+
      (LABEL[pr]||pr)+'</span></td><td>'+esc(r.mca_modules)+'<div class="ev">'+
      esc(r.mca_evidence)+'</div></td><td>'+esc(r.hub_modules)+'<div class="ev">'+
      esc(r.hub_evidence)+'</div></td><td>'+esc(r.note)+'</td></tr>'});
  document.getElementById('tb').innerHTML=rows.join('');
  document.getElementById('n').textContent='匹配 '+hit.length+' / '+DATA.length+' 条';
  document.getElementById('more').textContent=
    hit.length>CAP?'只显示前 '+CAP+' 条，请继续收窄过滤条件':'';
}
function deb(){clearTimeout(t);t=setTimeout(render,150)}
document.getElementById('q').addEventListener('input',deb);
document.getElementById('dom').addEventListener('change',render);
document.getElementById('par').addEventListener('change',render);
render();
</script></body></html>""".replace("__SUMMARY__", summary).replace("__NOW__", now()) \
        .replace("__DOMS__", dom_opts).replace("__DATA__", payload)


def write_json(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def render(args):
    pipeline = build_overview() if args.view == "overview" else build_repo_view(args.view)
    write_json(os.path.join(args.out_dir, "pipeline.json"), pipeline)
    msg = f"[{now()}] pipeline.json({args.view}): {len(pipeline['skills'])} 节点"
    lineage = build_lineage(args.lineage)
    if lineage:
        write_json(os.path.join(args.out_dir, "lineage.json"), lineage)
        msg += f" | lineage.json({args.lineage}): {len(lineage['nodes'])} 节点"
    else:
        msg += " | 无缺口可画（或 capabilities.csv 还没数据），跳过 lineage.json"
    if cap_rows():
        html = build_matrix_html()
        with open(os.path.join(args.out_dir, "matrix.html"), "w", encoding="utf-8") as f:
            f.write(html)
        msg += " | matrix.html 已生成"
    print(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, help="skillflow-monitor/public/status 目录")
    ap.add_argument("--view", choices=["overview", "mca", "hub"], default="overview")
    ap.add_argument("--lineage", choices=["gaps", "all"], default="gaps",
                    help="血缘图画什么：gaps=只画缺口(默认，图才看得清)；all=全画")
    ap.add_argument("--watch", type=int, default=0)
    args = ap.parse_args()

    if args.watch > 0:
        print(f"watch 模式：每 {args.watch}s 刷新，Ctrl+C 退出。")
        try:
            while True:
                render(args)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            sys.exit(0)
    else:
        render(args)


if __name__ == "__main__":
    main()
