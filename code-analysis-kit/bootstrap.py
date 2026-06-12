#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为一个代码库生成分析工作区：work/<name>/ 下的 MAP.md、PROGRESS.md、SYMBOLS.txt (+ chunks/)。
每个要分析的仓库各跑一次。纯标准库，跨平台。

用法（Windows 示例）：
  python code-analysis-kit\\bootstrap.py --name mca --root D:\\code\\mca --preset java
  python code-analysis-kit\\bootstrap.py --name hub --root D:\\code\\hub --preset as400

参数：
  --name      工作区名（mca / hub），决定 work/<name>/ 目录
  --root      该代码库根目录
  --preset    java | as400 | all（决定统计哪些扩展名），或用 --exts 自定义
  --exts      逗号分隔扩展名，覆盖 preset
  --min       目录少于多少文件就【归并进父目录单元】（默认 3）。任何文件都不会被丢弃。
  --chunk     单目录超过多少文件就拆块（默认 50）
  --top       MAP.md 里目录排行显示多少行（默认 80）
  --include-tests  测试目录也纳入分析（默认 SKIP）
  --no-sniff       关闭 sql/xml 内容嗅探（预分类用）
  --no-scan        关闭 LOC/符号扫描（地图会退化成只有文件数，不建议关）

产物：
  MAP.md       目录地图：文件数 + 真实代码行数 + 类/端点/表 符号统计
  SYMBOLS.txt  符号索引（文件\\t类别\\t名称），模型可 grep 检索，不必读源码
  PROGRESS.md  任务队列：预分类（SKIP沉淀物/合并迁移链/精读指令）+ 大目录拆块
  MAP-dirs.txt / MAP-merged.txt  全量目录清单 / 小目录归并记录（审计用）
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
    visited = set()  # 防 Windows junction / 符号链接造成的死循环
    for dirpath, dirnames, filenames in os.walk(root):
        real = os.path.realpath(dirpath)
        if real in visited:
            dirnames[:] = []
            continue
        visited.add(real)
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS and not d.startswith(".")
                       and not os.path.islink(os.path.join(dirpath, d))]
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


def ext_of(rel):
    fn = rel.rsplit("/", 1)[-1]
    return fn.rsplit(".", 1)[-1].lower() if "." in fn else ""


# ---------- 内容扫描：LOC + 符号索引（地图精确化的核心） ----------
JAVA_EXT = {"java", "kt", "groovy"}
SQL_EXT = {"sql"}
XML_EXT = {"xml"}
RPG_EXT = {"rpg", "rpgle", "sqlrpgle", "rpg38", "rpglemod", "clp", "clle", "cl",
           "cbl", "cob", "cblle", "mbr", "src"}
DDS_EXT = {"dds", "pf", "lf", "dspf", "prtf"}

RE_JAVA_TYPE = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)")
RE_JAVA_IMPORT = re.compile(r"^import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
RE_JAVA_EP = re.compile(r'@(?:RequestMapping|GetMapping|PostMapping|PutMapping|'
                        r'DeleteMapping|PatchMapping)\s*\(\s*(?:value\s*=\s*)?"([^"]*)"')
RE_JAVA_TBL = re.compile(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"')
RE_JAVA_ENTITY = re.compile(r"@Entity\b")
RE_SQL_OBJ = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW|PROCEDURE|FUNCTION|TRIGGER)'
                        r'\s+([\w."$#@]+)', re.I)
RE_XML_MAPPER = re.compile(r'<mapper\s+namespace="([^"]+)"')
RE_RPG_CALL = re.compile(r"\bCALL\b\s+(?:PGM\()?'?([A-Z0-9_$#@]+)'?\)?", re.I)
RE_DDS_REC = re.compile(r"^\s*A\s+R\s+([A-Z0-9_$#@]+)", re.I | re.M)


MAX_SCAN_BYTES = 4 * 1024 * 1024  # 单文件最多解析前 4MB（源码文件不可能这么大；大的是dump/日志）


def scan_file(path, ext, stem):
    """读一遍文件，返回 (行数, [(kind, name), ...])。正则是启发式，够用即可。
    超过 MAX_SCAN_BYTES 的部分只数行数，不再做符号提取，防止数据 dump 卡死扫描。"""
    try:
        with open(path, "rb") as fb:
            data = fb.read(MAX_SCAN_BYTES)
            extra = 0
            while True:  # 剩余部分流式数行，不进内存
                chunk = fb.read(1 << 20)
                if not chunk:
                    break
                extra += chunk.count(b"\n")
        text = data.decode("utf-8", errors="ignore")
    except OSError:
        return 0, []
    loc = text.count("\n") + extra + (1 if text and not text.endswith("\n") else 0)
    syms = []
    if ext in JAVA_EXT:
        syms += [("type", n) for n in RE_JAVA_TYPE.findall(text)]
        syms += [("import", n) for n in RE_JAVA_IMPORT.findall(text)]
        syms += [("endpoint", n or "/") for n in RE_JAVA_EP.findall(text)]
        syms += [("table", n) for n in RE_JAVA_TBL.findall(text)]
        if RE_JAVA_ENTITY.search(text) and not RE_JAVA_TBL.search(text):
            syms.append(("table", stem))
    elif ext in SQL_EXT:
        syms += [("table" if k.upper() in ("TABLE", "VIEW") else "proc", n.strip('"'))
                 for k, n in RE_SQL_OBJ.findall(text)]
    elif ext in XML_EXT:
        syms += [("mapper", n) for n in RE_XML_MAPPER.findall(text)]
    elif ext in RPG_EXT:
        syms.append(("program", stem))
        syms += [("call", n.upper()) for n in set(RE_RPG_CALL.findall(text))]
    elif ext in DDS_EXT:
        syms.append(("table", stem.upper()))
        syms += [("recfmt", n.upper()) for n in RE_DDS_REC.findall(text)]
    return loc, syms[:200]  # 单文件符号上限，防异常文件


def scan_contents(root, src):
    """全库一遍扫描。返回 (loc_by_dir, sym_count_by_dir_kind, symbols_lines)。"""
    loc_by_dir = Counter()
    sym_cnt = Counter()  # (dir, kind) -> n
    sym_lines = []
    root = os.path.abspath(root)
    total = len(src)
    for i, rel in enumerate(src, 1):
        if i % 2000 == 0 or i == total:
            print(f"  ... {i}/{total} 文件已扫描", flush=True)
        d = dir_of(rel)
        ext = ext_of(rel)
        stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        loc, syms = scan_file(os.path.join(root, rel), ext, stem)
        loc_by_dir[d] += loc
        for kind, name in syms:
            sym_cnt[(d, kind)] += 1
            sym_lines.append(f"{rel}\t{kind}\t{name}")
    return loc_by_dir, sym_cnt, sym_lines


# ---------- 小目录归并：任何文件都不丢，--min 只决定"独立单元"门槛 ----------
def merge_small(by_dir, min_files):
    """少于 min_files 的目录把文件归并到最近的祖先单元。返回 (units, merged_log)。"""
    units = {d: list(fs) for d, fs in by_dir.items()}
    merged = []  # (小目录, 归并目标)
    for d in sorted(units, key=lambda x: -x.count("/")):  # 最深的先处理，可级联上浮
        if d == "." or len(units[d]) >= min_files:
            continue
        parts = d.split("/")
        target = "."
        for i in range(len(parts) - 1, 0, -1):
            anc = "/".join(parts[:i])
            if anc in units:
                target = anc
                break
        units.setdefault(target, []).extend(units.pop(d))
        merged.append((d, target))
    return units, merged


# ---------- 预分类：把历史沉淀物在排队阶段就标出来 ----------
TEST_PAT = re.compile(r"(^|/)(src/test|tests?|__tests__|testdata|fixtures?|mocks?|mockdata|samples?)(/|$)", re.I)
GEN_PAT = re.compile(r"(^|/)(generated|gen|\.?codegen|autogen)(/|$)", re.I)
MIG_PAT = re.compile(r"(^|/)(db/)?(migrations?|flyway|liquibase|changelogs?)(/|$)", re.I)


def sniff_head(path, n=16384):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read(n).upper()
    except OSError:
        return ""


def classify_unit(root, d, fs, include_tests, do_sniff):
    """返回 (status, merge, note)。merge=True 表示整目录合并为 1 个单元不拆块。"""
    if GEN_PAT.search(d):
        return "SKIP", False, "生成代码，自动跳过；要分析改回 TODO"
    if not include_tests and TEST_PAT.search(d):
        return "SKIP", False, "测试/夹具，自动跳过；要分析改回 TODO"
    if MIG_PAT.search(d):
        return "TODO", True, "【指令】历史迁移脚本链：不逐文件分析，叠加出最终表清单写入 inventory.csv 即可"

    exts = Counter(ext_of(f) for f in fs)
    if do_sniff and exts.get("sql", 0) >= 0.8 * len(fs):
        has_proc = has_ddl = has_data = False
        for rel in fs[:50]:
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


# ---------- 产出 ----------
def write_map(ws, name, root, src, entries, by_dir, merged, loc_by_dir, sym_cnt, top):
    by_ext = Counter(ext_of(f) for f in src)
    merged_files = sum(len(by_dir[d]) for d, _ in merged)
    total_loc = sum(loc_by_dir.values())

    def sym(d, kind):
        return sym_cnt.get((d, kind), 0)

    lines = [
        f"# 目录地图（MAP）— {name}\n",
        f"> 由 bootstrap.py 生成于 {date.today().isoformat()}。仓库根：{os.path.abspath(root)}",
        "> 这是“目录索引”，不是细节。符号可检索 SYMBOLS.txt，任务清单看 PROGRESS.md。\n",
        "## 规模概览\n```",
        f"源码文件总数: {len(src)}    总代码行数: {total_loc:,}\n",
        "按扩展名:",
    ]
    lines += [f"  {n:>7}  .{e}" for e, n in by_ext.most_common()]
    lines += ["```\n",
              "## 覆盖率（印证用）\n```",
              f"100% 文件进入任务队列（不丢任何文件）。",
              f"其中 {len(merged)} 个小目录（共 {merged_files} 个文件）已归并到父级单元，明细见 MAP-merged.txt",
              "```\n",
              f"## 各目录画像（按代码行数排序，前 {top}；全量见 MAP-dirs.txt）\n",
              "| 目录 | 文件 | 行数 | 类/程序 | 端点 | 表 |",
              "|------|-----:|-----:|--------:|-----:|---:|"]
    top_dirs = sorted(by_dir, key=lambda d: -loc_by_dir.get(d, 0))[:top]
    for d in top_dirs:
        lines.append(f"| {d} | {len(by_dir[d])} | {loc_by_dir.get(d, 0):,} "
                     f"| {sym(d, 'type') + sym(d, 'program')} | {sym(d, 'endpoint')} | {sym(d, 'table')} |")
    lines += ["", "## 可能的入口/构建文件\n```"]
    lines += [f"  {e}" for e in entries[:40]] or ["  (未识别到)"]
    lines += ["```"]
    with open(os.path.join(ws, "MAP.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    with open(os.path.join(ws, "MAP-dirs.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(f"{len(by_dir[d])}\t{loc_by_dir.get(d, 0)}\t{d}"
                          for d in sorted(by_dir, key=lambda x: -len(by_dir[x]))) + "\n")
    with open(os.path.join(ws, "MAP-merged.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(f"{d}\t->\t{t}" for d, t in merged) + "\n" if merged else "")


def write_progress(ws, name, root, units, by_dir, chunk, include_tests, do_sniff):
    dirs = sorted(units.items(), key=lambda x: -len(x[1]))
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
        has_merged_files = set(fs) != set(by_dir.get(d, []))  # 归并来的文件必须给清单
        if status == "SKIP" or merge or len(fs) <= chunk:
            uid += 1
            need_list = (merge and len(fs) > chunk) or (has_merged_files and status != "SKIP")
            rows.append((f"U{uid:03d}", d, len(fs), status, add_chunk(fs) if need_list else "", note))
        else:
            n_parts = math.ceil(len(fs) / chunk)
            for k in range(n_parts):
                uid += 1
                part = fs[k * chunk:(k + 1) * chunk]
                rows.append((f"U{uid:03d}", f"{d} [块{k + 1}/{n_parts}]", len(part), status,
                             add_chunk(part), note))

    lines = [
        f"# 分析进度与任务队列（PROGRESS）— {name}\n",
        f"NAME: {name}",
        f"ROOT: {os.path.abspath(root)}",
        "STATUS: IN_PROGRESS\n",
        "> 模型每轮：取第一个 TODO → 处理 → 改 DONE → 下一个。规则见 copilot-instructions.md。",
        "> 状态值：TODO / IN_PROGRESS / DONE / ERROR / SKIP。",
        "> “文件清单”列若有 chunks/Uxxx.txt，本单元只分析清单里那些文件（可能含归并来的子目录文件）。",
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
    ap.add_argument("--no-scan", action="store_true", help="关闭 LOC/符号扫描")
    args = ap.parse_args()

    exts_str = args.exts or PRESETS[args.preset]
    exts = {e.strip().lower().lstrip(".") for e in exts_str.split(",") if e.strip()}

    kit = os.path.dirname(os.path.abspath(__file__))
    ws = os.path.join(kit, "work", args.name)
    os.makedirs(ws, exist_ok=True)
    os.makedirs(os.path.join(kit, "notes", args.name), exist_ok=True)
    os.makedirs(os.path.join(kit, "evidence", args.name), exist_ok=True)

    print(f"扫描 {args.root} （preset={args.preset}）...", flush=True)
    src, entries = collect(args.root, exts)

    by_dir = {}
    for f in src:
        by_dir.setdefault(dir_of(f), []).append(f)

    if args.no_scan:
        loc_by_dir, sym_cnt, sym_lines = Counter(), Counter(), []
    else:
        print(f"内容扫描 {len(src)} 个文件（LOC + 符号索引）...", flush=True)
        loc_by_dir, sym_cnt, sym_lines = scan_contents(args.root, src)
        with open(os.path.join(ws, "SYMBOLS.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(sym_lines) + "\n")

    units, merged = merge_small(by_dir, args.min)
    write_map(ws, args.name, args.root, src, entries, by_dir, merged, loc_by_dir, sym_cnt, args.top)
    n_units, stats = write_progress(ws, args.name, args.root, units, by_dir, args.chunk,
                                    args.include_tests, not args.no_sniff)

    print(f"完成：{len(src)} 个源码文件（100% 进队列）→ {n_units} 个分析单元；"
          f"{len(merged)} 个小目录已归并")
    print(f"预分类：{dict(stats)}（SKIP 行请在 PROGRESS.md 里人工复核）")
    if not args.no_scan:
        kinds = Counter(k for (_, k) in sym_cnt.elements())
        print(f"符号索引：{dict(kinds)} → {os.path.join(ws, 'SYMBOLS.txt')}")
    print(f"  - {os.path.join(ws, 'MAP.md')}")
    print(f"  - {os.path.join(ws, 'PROGRESS.md')}")
    if len(src) == 0:
        print("\n[提示] 没扫到源码。检查 --root，或用 --exts/--preset 指定扩展名。")


if __name__ == "__main__":
    main()
