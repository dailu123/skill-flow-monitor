#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分诊器：千万行级仓库专用。把"全量精读"降级为"机器清点 + LLM 抽样"，
在【不重置已有进度】的前提下改写 PROGRESS.md 里的 TODO 行。

用法（bootstrap 之后、任何时候都可以跑，DONE 的行不会被碰）：
  python code-analysis-kit\\triage.py --name hub
  python code-analysis-kit\\triage.py --name mca

做四件事：
  1. PF/DDS 表定义 → 机器直接提取 evidence/<name>/tables.csv（表/记录格式/字段/长度），
     对应单元降级为"补业务含义即可，不逐文件读"
  2. 克隆检测 → 内容归一化哈希分家族，chunk 清单改写为"每族一个代表"
  3. CALL/import 引用度 → 零引用且无入口特征的单元降级为"轻量登记"
  4. 产出 work/<name>/TRIAGE.md：削减统计（哪些不用精读了、省了多少行）
"""
import argparse
import hashlib
import os
import re
from collections import Counter, defaultdict

KIT = os.path.dirname(os.path.abspath(__file__))
DDS_EXT = {"dds", "pf", "lf", "dspf", "prtf"}
PRUNE_DIRS = {
    "node_modules", ".git", "vendor", "dist", "build", "__pycache__",
    ".venv", "venv", "target", "code-analysis-kit", ".idea", ".vscode",
    ".mypy_cache", ".pytest_cache", "site-packages", "bin", "obj", ".gradle",
}

RE_DDS_REC = re.compile(r"^\s{0,6}A\s+R\s+([A-Z0-9_$#@]+)", re.I)
RE_DDS_FLD = re.compile(r"^\s{0,6}A\s+([A-Z0-9_$#@]{2,10})\s+(\d+)\s*([A-Z]?)", re.I)


def ext_of(rel):
    fn = rel.rsplit("/", 1)[-1]
    return fn.rsplit(".", 1)[-1].lower() if "." in fn else ""


def dir_of(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else "."


# ---------- PROGRESS 读写（只动 TODO 行） ----------
def load_progress(name):
    path = os.path.join(KIT, "work", name, "PROGRESS.md")
    lines = open(path, encoding="utf-8").read().splitlines()
    rows = []  # (行号, cells)
    root = None
    for i, line in enumerate(lines):
        m = re.match(r"^ROOT:\s*(.+)$", line)
        if m:
            root = m.group(1).strip()
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 7 and cells[0].startswith("U"):
            rows.append((i, cells))
    return path, lines, rows, root


def unit_files(name, root, cells, by_dir):
    lst = cells[4]
    if lst.startswith("chunks/"):
        p = os.path.join(KIT, "work", name, lst.replace("/", os.sep))
        if os.path.exists(p):
            return [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    d = re.sub(r"\s*\[块\d+/\d+\]\s*$", "", cells[1])
    return by_dir.get(d, [])


# ---------- 内容扫描：LOC + 归一化哈希 + DDS 字段 ----------
def norm_hash(text):
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.md5(t.encode("utf-8", "ignore")).hexdigest()


def scan(root):
    by_dir, loc, h, dds_rows = defaultdict(list), {}, {}, []
    root = os.path.abspath(root)
    files = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in PRUNE_DIRS and not d.startswith(".")]
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root).replace("\\", "/")
            files.append(rel)
    total = len(files)
    for i, rel in enumerate(sorted(files), 1):
        if i % 5000 == 0 or i == total:
            print(f"  ... {i}/{total} 文件已扫描", flush=True)
        try:
            with open(os.path.join(root, rel), "rb") as f:
                data = f.read(256 * 1024)  # 归一化哈希看前 256KB 足够
                extra = 0
                while True:
                    c = f.read(1 << 20)
                    if not c:
                        break
                    extra += c.count(b"\n")
        except OSError:
            continue
        text = data.decode("utf-8", "ignore")
        by_dir[dir_of(rel)].append(rel)
        loc[rel] = text.count("\n") + extra
        h[rel] = norm_hash(text)
        if ext_of(rel) in DDS_EXT:  # 表定义机器直接提取
            stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0].upper()
            rec = ""
            for line in text.splitlines():
                m = RE_DDS_REC.match(line)
                if m:
                    rec = m.group(1).upper()
                    continue
                m = RE_DDS_FLD.match(line)
                if m and m.group(1).upper() != "R":
                    dds_rows.append((stem, rec, m.group(1).upper(), m.group(2),
                                     m.group(3).upper(), rel))
    return by_dir, loc, h, dds_rows


def fan_in_map(name):
    """SYMBOLS.txt 的 call/import → 每个文件被引用次数；endpoint/dspf 视为入口。"""
    path = os.path.join(KIT, "work", name, "SYMBOLS.txt")
    defs, refs, entry_files = defaultdict(set), Counter(), set()
    if not os.path.exists(path):
        return {}, entry_files
    syms = [l.rstrip("\n").split("\t") for l in open(path, encoding="utf-8")]
    syms = [x for x in syms if len(x) == 3]
    for f, k, n in syms:
        if k == "program":
            defs[n.upper()].add(f)
        elif k == "type":
            defs[n].add(f)
        elif k == "endpoint":
            entry_files.add(f)
    for f, k, n in syms:
        if k == "call":
            refs[n.upper()] += 1
        elif k == "import":
            refs[n.rsplit(".", 1)[-1]] += 1
    fan = Counter()
    for nme, fs in defs.items():
        for f in fs:
            fan[f] += refs.get(nme, 0)
    return fan, entry_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--dup-ratio", type=float, default=0.3, help="重复文件占比超过此值就去重清单")
    ap.add_argument("--pf-ratio", type=float, default=0.7, help="DDS 文件占比超过此值就降级为表定义单元")
    args = ap.parse_args()

    path, lines, rows, root = load_progress(args.name)
    if not root or not os.path.isdir(root):
        raise SystemExit(f"PROGRESS 里的 ROOT 不可用: {root}")
    print(f"分诊 {args.name}（ROOT={root}）...", flush=True)
    by_dir, loc, hashes, dds_rows = scan(root)
    fan, entry_files = fan_in_map(args.name)

    # tables.csv：机器提取的全部表定义
    if dds_rows:
        tp = os.path.join(KIT, "evidence", args.name, "tables.csv")
        os.makedirs(os.path.dirname(tp), exist_ok=True)
        with open(tp, "w", encoding="utf-8-sig", newline="") as f:
            f.write("table,recfmt,field,len,type,source,business_meaning\n")
            for r in dds_rows:
                f.write(",".join(r) + ",\n")
        print(f"tables.csv：{len({r[0] for r in dds_rows})} 张表 / {len(dds_rows)} 个字段已自动提取")

    seen_hash, stats = set(), Counter()
    saved_loc = 0
    chunks_dir = os.path.join(KIT, "work", args.name, "chunks")

    for li, cells in rows:
        if cells[3] != "TODO":      # DONE/SKIP/IN_PROGRESS 一律不碰
            seen_hash.update(hashes.get(f) for f in unit_files(args.name, root, cells, by_dir))
            continue
        fs = unit_files(args.name, root, cells, by_dir)
        if not fs:
            continue
        n = len(fs)
        note = cells[6]
        pf_n = sum(1 for f in fs if ext_of(f) in DDS_EXT)
        uniq, dup_loc = [], 0
        for f in fs:
            hsh = hashes.get(f)
            if hsh in seen_hash:
                dup_loc += loc.get(f, 0)
            else:
                uniq.append(f)
                seen_hash.add(hsh)

        if pf_n >= args.pf_ratio * n:
            tag = "【指令】表定义单元：字段已机器提取到 evidence/%s/tables.csv，只为每张表补一句业务含义，不逐文件读" % args.name
            stats["表定义降级"] += 1
            saved_loc += sum(loc.get(f, 0) for f in fs)
        elif n - len(uniq) >= args.dup_ratio * n:
            lst = f"chunks/{cells[0]}-dedup.txt"
            os.makedirs(chunks_dir, exist_ok=True)
            with open(os.path.join(KIT, "work", args.name, lst.replace("/", os.sep)),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(uniq) + "\n")
            cells[4] = lst
            tag = f"【指令】清单已克隆去重（代表 {len(uniq)}/原 {n}）：只读清单内文件，克隆家族在笔记里说明一句"
            stats["克隆去重"] += 1
            saved_loc += dup_loc
        elif all(fan.get(f, 0) == 0 for f in fs) and not any(f in entry_files for f in fs):
            tag = "【指令】零引用单元：只登记 inventory 和一句话职责，不做控制流分析（疑似死代码，在笔记里标注）"
            stats["零引用降级"] += 1
            saved_loc += int(sum(loc.get(f, 0) for f in fs) * 0.7)
        else:
            stats["保持精读"] += 1
            continue

        cells[6] = (note + "；" + tag) if (note and tag not in note) else tag
        lines[li] = "| " + " | ".join(cells) + " |"

    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    tpath = os.path.join(KIT, "work", args.name, "TRIAGE.md")
    with open(tpath, "w", encoding="utf-8") as f:
        f.write(f"# 分诊报告 — {args.name}\n\n")
        f.write(f"- 单元处置：{dict(stats)}\n")
        f.write(f"- 估算免精读代码行：{saved_loc:,}\n")
        f.write(f"- 表定义：{len({r[0] for r in dds_rows})} 张表已机器提取（evidence/{args.name}/tables.csv）\n")
        f.write("\n> DONE/SKIP 行未被改动；TODO 行的指令由 LLM 在分析时执行。重跑本脚本是幂等的。\n")
    print(f"分诊完成：{dict(stats)}，估算免精读 {saved_loc:,} 行 → {tpath}")


if __name__ == "__main__":
    main()
