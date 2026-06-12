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
  --top       MAP.md 里目录排行显示多少行（默认 80）
  --include-tests  测试目录也纳入分析（默认 SKIP）
  --no-sniff       关闭 sql/xml 内容嗅探（嗅探只读每文件头部16KB，通常没必要关）

预分类：队列生成时自动把"历史沉淀物"标出来，模型不浪费轮次：
  - 测试/夹具/生成物目录 → 状态 SKIP（留痕可审计，要分析就手动改回 TODO）
  - 迁移脚本链(flyway/liquibase/migrations) → 合并成 1 个单元，指令=只提取最终表清单
  - 纯 INSERT 种子数据 SQL → SKIP；含存储过程 SQL → 标记必须精读
  - MyBatis mapper XML → 标记重点提取表与SQL
"""
import argparse
import math
import os
import re
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


def write_map(ws, name, root, src, entries, min_files, top):
    by_ext = Counter(f.rsplit(".", 1)[-1].lower() for f in src)
    by_dir = Counter(dir_of(f) for f in src)
    excluded = {d: n for d, n in by_dir.items() if n < min_files}
    excl_files = sum(excluded.values())
    covered_pct = round(100 * (len(src) - excl_files) / len(src), 1) if src else 0
    lines = [
        f"# 目录地图（MAP）— {name}\n",
        f"> 由 bootstrap.py 生成于 {date.today().isoformat()}。仓库根：{os.path.abspath(root)}",
        "> 这是“目录索引”，不是细节。细节看 notes/，完整任务清单看 PROGRESS.md。\n",
        "## 规模概览\n```",
        f"源码文件总数: {len(src)}\n",
        "按扩展名:",
    ]
    lines += [f"  {n:>7}  .{e}" for e, n in by_ext.most_common()]
    lines += ["```\n",
              "## 覆盖率（印证用）\n```",
              f"目录总数: {len(by_dir)}",
              f"进入任务队列: {len(by_dir) - len(excluded)} 个目录 / {len(src) - excl_files} 个文件（覆盖 {covered_pct}%）",
              f"被 --min {min_files} 排除: {len(excluded)} 个目录 / {excl_files} 个文件",
              "```"]
    if excluded:
        lines += ["", f"被排除的目录（人工确认这些可以不分析；不行就调小 --min 重跑）:", "```"]
        lines += [f"  {n:>7}  {d}" for d, n in sorted(excluded.items(), key=lambda x: -x[1])[:50]]
        if len(excluded) > 50:
            lines += [f"  ... 还有 {len(excluded) - 50} 个，完整清单见 MAP-excluded.txt"]
        lines += ["```"]
        with open(os.path.join(ws, "MAP-excluded.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(f"{n}\t{d}" for d, n in sorted(excluded.items(), key=lambda x: -x[1])) + "\n")
    lines += ["", f"## 各目录代码量（按文件数排序，前 {top}；完整目录清单见 MAP-dirs.txt）\n```"]
    lines += [f"  {n:>7}  {d}" for d, n in by_dir.most_common(top)]
    lines += ["```\n", "## 可能的入口/构建文件\n```"]
    lines += [f"  {e}" for e in entries[:40]] or ["  (未识别到)"]
    lines += ["```"]
    with open(os.path.join(ws, "MAP.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    # 不省略的全量目录清单（给人审计 / 给模型按需 grep，不占上下文）
    with open(os.path.join(ws, "MAP-dirs.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(f"{n}\t{d}" for d, n in by_dir.most_common()) + "\n")


# ---------- 预分类：把历史沉淀物在排队阶段就标出来 ----------
TEST_PAT = re.compile(r"(^|/)(src/test|tests?|__tests__|testdata|fixtures?|mocks?|mockdata|samples?)(/|$)", re.I)
GEN_PAT = re.compile(r"(^|/)(generated|gen|\.?codegen|autogen)(/|$)", re.I)
MIG_PAT = re.compile(r"(^|/)(db/)?(migrations?|flyway|liquibase|changelogs?)(/|$)", re.I)


def sniff_head(path, n=16384):
    """只读文件头部，避免拖慢扫描。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read(n).upper()
    except OSError:
        return ""


def classify_unit(root, d, fs, include_tests, do_sniff):
    """返回 (status, merge, note)。
    status: TODO|SKIP；merge=True 表示整目录合并为 1 个单元不拆块；note 进“一句话摘要”列。"""
    if GEN_PAT.search(d):
        return "SKIP", False, "生成代码，自动跳过；要分析改回 TODO"
    if not include_tests and TEST_PAT.search(d):
        return "SKIP", False, "测试/夹具，自动跳过；要分析改回 TODO"
    if MIG_PAT.search(d):
        return "TODO", True, "【指令】历史迁移脚本链：不逐文件分析，叠加出最终表清单写入 inventory.csv 即可"

    exts = Counter(f.rsplit(".", 1)[-1].lower() for f in fs)
    if do_sniff and exts.get("sql", 0) >= 0.8 * len(fs):
        has_proc = has_ddl = has_data = False
        for rel in fs[:50]:  # 抽样嗅探，控制速度
            head = sniff_head(os.path.join(root, rel))
            if re.search(r"CREATE\s+(OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION|TRIGGER|PACKAGE)", head):
                has_proc = True
            if re.search(r"(CREATE|ALTER)\s+TABLE|CREATE\s+(MATERIALIZED\s+)?VIEW", head):
                has_ddl = True
            if "INSERT INTO" in head:
                has_data = True
        if has_proc:
            return "TODO", False, "【指令】含存储过程/函数：必须精读，业务规则藏在这里"
        if has_ddl:
            return "TODO", True, "【指令】DDL为主：提取表清单写入 inventory.csv 即可，不逐文件分析"
        if has_data:
            return "SKIP", False, "纯INSERT种子数据，自动跳过；要分析改回 TODO"

    if do_sniff and exts.get("xml", 0) >= 0.8 * len(fs):
        for rel in fs[:20]:
            if "<MAPPER" in sniff_head(os.path.join(root, rel), 4096):
                return "TODO", False, "【指令】MyBatis mapper：重点提取表名与SQL业务查询"
        return "TODO", True, "【指令】配置XML：快速过一遍提取数据源/作业配置即可，不逐文件分析"

    return "TODO", False, ""


def write_progress(ws, name, root, src, min_files, chunk, include_tests, do_sniff):
    """生成任务队列。预分类标注 + 超大目录拆块（文件清单写到 chunks/Uxxx.txt）。"""
    by_dir = {}
    for f in src:
        by_dir.setdefault(dir_of(f), []).append(f)
    dirs = [(d, fs) for d, fs in by_dir.items() if len(fs) >= min_files]
    dirs.sort(key=lambda x: -len(x[1]))

    chunks_dir = os.path.join(ws, "chunks")
    rows, uid = [], 0
    stats = Counter()

    def add_chunk(part):
        lst = f"chunks/U{uid:03d}.txt"
        os.makedirs(chunks_dir, exist_ok=True)
        with open(os.path.join(ws, lst.replace("/", os.sep)), "w", encoding="utf-8") as cf:
            cf.write("\n".join(part) + "\n")
        return lst

    for d, fs in dirs:
        status, merge, note = classify_unit(os.path.abspath(root), d, fs, include_tests, do_sniff)
        stats["跳过" if status == "SKIP" else ("合并" if merge else ("指令" if note else "常规"))] += 1
        if status == "SKIP" or merge or len(fs) <= chunk:
            uid += 1
            lst = add_chunk(fs) if (merge and len(fs) > chunk) else ""
            rows.append((f"U{uid:03d}", d, len(fs), status, lst, note))
        else:  # 常规大目录拆块
            n_parts = math.ceil(len(fs) / chunk)
            for k in range(n_parts):
                uid += 1
                part = fs[k * chunk:(k + 1) * chunk]
                rows.append((f"U{uid:03d}", f"{d} [块{k + 1}/{n_parts}]", len(part), status, add_chunk(part), note))

    lines = [
        f"# 分析进度与任务队列（PROGRESS）— {name}\n",
        f"NAME: {name}",
        f"ROOT: {os.path.abspath(root)}",
        "STATUS: IN_PROGRESS\n",
        "> 模型每轮：取第一个 TODO → 处理 → 改 DONE → 下一个。规则见 copilot-instructions.md。",
        "> 状态值：TODO / IN_PROGRESS / DONE / ERROR / SKIP。",
        "> “文件清单”列若有 chunks/Uxxx.txt，本单元只分析清单里那些文件。",
        "> “一句话摘要”列以【指令】开头的，按指令执行后再覆盖为实际摘要。",
        "> SKIP 行是预分类自动跳过的（测试/生成物/种子数据），人工复核后想分析就改回 TODO。\n",
        "## 队列\n",
        "| ID | 单元(目录) | 文件数 | 状态 | 文件清单 | 笔记 | 一句话摘要 |",
        "|----|-----------|--------|------|----------|------|-----------|",
    ]
    for rid, d, n, status, lst, note in rows:
        lines.append(f"| {rid} | {d} | {n} | {status} | {lst} |  | {note} |")
    with open(os.path.join(ws, "PROGRESS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(rows), stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="工作区名，如 mca / hub")
    ap.add_argument("--root", required=True)
    ap.add_argument("--preset", choices=sorted(PRESETS), default="all")
    ap.add_argument("--exts", default="")
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--top", type=int, default=80, help="MAP.md 里目录排行显示多少行")
    ap.add_argument("--include-tests", action="store_true", help="测试目录也纳入分析")
    ap.add_argument("--no-sniff", action="store_true", help="关闭 sql/xml 内容嗅探")
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
    write_map(ws, args.name, args.root, src, entries, args.min, args.top)
    n_units, stats = write_progress(ws, args.name, args.root, src, args.min, args.chunk,
                                    args.include_tests, not args.no_sniff)

    print(f"完成：{len(src)} 个源码文件 → {n_units} 个分析单元")
    print(f"预分类：{dict(stats)}（SKIP 行请在 PROGRESS.md 里人工复核）")
    print(f"  - {os.path.join(ws, 'MAP.md')}")
    print(f"  - {os.path.join(ws, 'PROGRESS.md')}")
    if len(src) == 0:
        print("\n[提示] 没扫到源码。检查 --root，或用 --exts/--preset 指定扩展名。")


if __name__ == "__main__":
    main()
