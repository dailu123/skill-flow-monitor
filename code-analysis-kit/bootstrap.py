#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为一个代码库生成分析工作区：work/<name>/MAP.md + PROGRESS.md (+ chunks/)。
每个要分析的仓库各跑一次。纯标准库，跨平台。

用法（Windows 示例）：
  python code-analysis-kit\\bootstrap.py --name mca --root D:\\code\\mca --preset java
  python code-analysis-kit\\bootstrap.py --name hub --root D:\\code\\hub --preset as400

参数：
  --name      工作区名（mca / hub），决定 work/<name>/ 目录
  --root      该代码库根目录
  --preset    java | as400 | all（决定统计哪些扩展名），或用 --exts 自定义
  --exts      逗号分隔扩展名，覆盖 preset
  --min       目录至少多少源码文件才进队列（默认 3）
  --chunk     单目录超过多少文件就拆块（默认 50；AS/400 一库几千 member 必须拆）
"""
import argparse
import math
import os
from collections import Counter
from datetime import date

PRESETS = {
    "java": "java,kt,groovy,jsp,sql,xml",
    "as400": "rpg,rpgle,sqlrpgle,rpg38,rpglemod,clp,clle,cl,cmd,cbl,cob,cblle,"
             "dds,pf,lf,dspf,prtf,sql,mbr,src,txt",
    "all": "py,go,ts,tsx,js,jsx,java,rb,rs,cpp,cc,c,h,hpp,kt,scala,php,cs,sql",
}

PRUNE_DIRS = {
    "node_modules", ".git", "vendor", "dist", "build", "__pycache__",
    ".venv", "venv", "target", "code-analysis-kit", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache", "site-packages", "bin", "obj", ".gradle",
}

ENTRY_NAMES = {"__main__.py", "manage.py", "pom.xml", "build.gradle", "settings.gradle"}
ENTRY_STEMS = {"main", "app", "index", "cli", "server", "application"}


def collect(root, exts):
    src, entries = [], []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
            if ext in exts:
                src.append(rel)
            stem = fn.rsplit(".", 1)[0].lower()
            if fn.lower() in ENTRY_NAMES or stem in ENTRY_STEMS:
                entries.append(rel)
    return sorted(src), sorted(entries)


def dir_of(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else "."


def write_map(ws, name, root, src, entries):
    by_ext = Counter(f.rsplit(".", 1)[-1].lower() for f in src)
    by_dir = Counter(dir_of(f) for f in src)
    lines = [
        f"# 目录地图（MAP）— {name}\n",
        f"> 由 bootstrap.py 生成于 {date.today().isoformat()}。仓库根：{os.path.abspath(root)}",
        "> 这是“目录索引”，不是细节。细节看 notes/。\n",
        "## 规模概览\n```",
        f"源码文件总数: {len(src)}\n",
        "按扩展名:",
    ]
    lines += [f"  {n:>7}  .{e}" for e, n in by_ext.most_common()]
    lines += ["```\n", "## 各目录代码量（按文件数排序，前 80）\n```"]
    lines += [f"  {n:>7}  {d}" for d, n in by_dir.most_common(80)]
    lines += ["```\n", "## 可能的入口/构建文件\n```"]
    lines += [f"  {e}" for e in entries[:40]] or ["  (未识别到)"]
    lines += ["```"]
    with open(os.path.join(ws, "MAP.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_progress(ws, name, root, src, min_files, chunk):
    """生成任务队列。超大目录拆块：文件清单写到 chunks/Uxxx.txt。"""
    by_dir = {}
    for f in src:
        by_dir.setdefault(dir_of(f), []).append(f)
    dirs = [(d, fs) for d, fs in by_dir.items() if len(fs) >= min_files]
    dirs.sort(key=lambda x: -len(x[1]))

    chunks_dir = os.path.join(ws, "chunks")
    rows, uid = [], 0
    for d, fs in dirs:
        if len(fs) <= chunk:
            uid += 1
            rows.append((f"U{uid:03d}", d, len(fs), ""))
        else:  # 拆块
            n_parts = math.ceil(len(fs) / chunk)
            os.makedirs(chunks_dir, exist_ok=True)
            for k in range(n_parts):
                uid += 1
                part = fs[k * chunk:(k + 1) * chunk]
                lst = f"chunks/U{uid:03d}.txt"
                with open(os.path.join(ws, lst.replace("/", os.sep)), "w", encoding="utf-8") as cf:
                    cf.write("\n".join(part) + "\n")
                rows.append((f"U{uid:03d}", f"{d} [块{k + 1}/{n_parts}]", len(part), lst))

    lines = [
        f"# 分析进度与任务队列（PROGRESS）— {name}\n",
        f"NAME: {name}",
        f"ROOT: {os.path.abspath(root)}",
        "STATUS: IN_PROGRESS\n",
        "> 模型每轮：取第一个 TODO → 处理 → 改 DONE → 下一个。规则见 copilot-instructions.md。",
        "> 状态值：TODO / IN_PROGRESS / DONE / ERROR。",
        "> “文件清单”列若有 chunks/Uxxx.txt，本单元只分析清单里那些文件。\n",
        "## 队列\n",
        "| ID | 单元(目录) | 文件数 | 状态 | 文件清单 | 笔记 | 一句话摘要 |",
        "|----|-----------|--------|------|----------|------|-----------|",
    ]
    for rid, d, n, lst in rows:
        lines.append(f"| {rid} | {d} | {n} | TODO | {lst} |  |  |")
    with open(os.path.join(ws, "PROGRESS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="工作区名，如 mca / hub")
    ap.add_argument("--root", required=True)
    ap.add_argument("--preset", choices=sorted(PRESETS), default="all")
    ap.add_argument("--exts", default="")
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--chunk", type=int, default=50)
    args = ap.parse_args()

    exts_str = args.exts or PRESETS[args.preset]
    exts = {e.strip().lower().lstrip(".") for e in exts_str.split(",") if e.strip()}

    kit = os.path.dirname(os.path.abspath(__file__))
    ws = os.path.join(kit, "work", args.name)
    os.makedirs(ws, exist_ok=True)
    os.makedirs(os.path.join(kit, "notes", args.name), exist_ok=True)
    os.makedirs(os.path.join(kit, "evidence", args.name), exist_ok=True)

    print(f"扫描 {args.root} （preset={args.preset}）...")
    src, entries = collect(args.root, exts)
    write_map(ws, args.name, args.root, src, entries)
    n_units = write_progress(ws, args.name, args.root, src, args.min, args.chunk)

    print(f"完成：{len(src)} 个源码文件 → {n_units} 个分析单元")
    print(f"  - {os.path.join(ws, 'MAP.md')}")
    print(f"  - {os.path.join(ws, 'PROGRESS.md')}")
    if len(src) == 0:
        print("\n[提示] 没扫到源码。检查 --root，或用 --exts/--preset 指定扩展名。")


if __name__ == "__main__":
    main()
