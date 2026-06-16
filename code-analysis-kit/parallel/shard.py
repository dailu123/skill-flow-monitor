#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把一个 PROGRESS.md 队列切成 N 个独立命名空间,供多个 VSCode 窗口并行跑;
跑完再合并回主仓库。每个分片是一个独立"仓库" R = <repo>__sK,
work/R、evidence/R、notes/R 全部独立,互不写同一文件 → 并行安全。

用法(在仓库根目录,Windows 同理把 / 换成 \\):
  # 切成 5 片(按"文件数"列做均衡装箱)
  python code-analysis-kit/parallel/shard.py split --repo mca --shards 5

  # 看进度(各分片 TODO/DONE)
  python code-analysis-kit/parallel/shard.py status --repo mca

  # 全部跑完后合并回 work/mca、evidence/mca、notes/mca
  python code-analysis-kit/parallel/shard.py merge --repo mca

  # (可选)清掉分片目录
  python code-analysis-kit/parallel/shard.py clean --repo mca
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # code-analysis-kit/
STATUSES = ("TODO", "IN_PROGRESS", "DONE", "SKIP", "ERROR")
SEP_RE = re.compile(r"^\|[\s:|-]+\|?\s*$")          # 表格分隔行 |----|----|
ROW_RE = re.compile(r"^\|.*\|\s*$")                  # 任意表格行


def work(repo):     return os.path.join(KIT, "work", repo)
def evidence(repo): return os.path.join(KIT, "evidence", repo)
def notes(repo):    return os.path.join(KIT, "notes", repo)
def progress(repo): return os.path.join(work(repo), "PROGRESS.md")
def ns_name(repo, k): return f"{repo}__s{k}"
def manifest_path(repo): return os.path.join(work(repo), "shards.json")


def parse_progress(text):
    """拆成 (preamble_lines, header_lines, data_rows)。header 含表头+分隔行。"""
    lines = text.splitlines()
    sep_i = next((i for i, l in enumerate(lines) if SEP_RE.match(l)), None)
    if sep_i is None:
        sys.exit("PROGRESS.md 里找不到表格分隔行(|----|),格式不对?")
    header = lines[:sep_i + 1]            # 含表头那行 + 分隔行
    data = [l for l in lines[sep_i + 1:] if ROW_RE.match(l) and l.strip("| ").strip()]
    return header, data


def row_status(row):
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    for c in cells:
        if c in STATUSES:
            return c
    return None


def row_id(row):
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    return cells[0] if cells else ""


def row_filecount(row):
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    for c in cells[1:]:
        if c.isdigit():
            return int(c)
    return 1


def cmd_split(repo, shards):
    if not os.path.exists(progress(repo)):
        sys.exit(f"找不到 {progress(repo)}")
    text = open(progress(repo), encoding="utf-8").read()
    header, data = parse_progress(text)

    # 均衡装箱:按文件数从大到小,每行丢进当前最轻的分片(LPT)
    buckets = [[] for _ in range(shards)]
    loads = [0] * shards
    for row in sorted(data, key=row_filecount, reverse=True):
        k = loads.index(min(loads))
        buckets[k].append(row)
        loads[k] += row_filecount(row)

    # 还原每片内部顺序(按 ID 排)让人看着舒服
    namespaces = []
    for k in range(shards):
        ns = ns_name(repo, k + 1)
        rows = sorted(buckets[k], key=row_id)
        _write_shard(repo, ns, header, rows)
        namespaces.append(ns)
        todo = sum(1 for r in rows if row_status(r) == "TODO")
        print(f"  {ns}: {len(rows)} 行 (TODO {todo}, 文件数合计 {loads[k]})")

    json.dump({"repo": repo, "shards": namespaces,
               "created": datetime.now().isoformat(timespec="seconds")},
              open(manifest_path(repo), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"清单写入 {manifest_path(repo)}")
    print(f"\n下一步:开 {shards} 个 VSCode 窗口都打开本仓库,装上 copilot-auto-continue 扩展,")
    print(f"设置 copilotAutoContinue.driver.repo = \"{repo}\",各窗口运行命令「启动并行驱动器」。")


def _write_shard(repo, ns, header, rows):
    """建 work/<ns>/(复制只读输入 + 写分片 PROGRESS),建空的 evidence/<ns>、notes/<ns>。"""
    os.makedirs(work(ns), exist_ok=True)
    os.makedirs(evidence(ns), exist_ok=True)
    os.makedirs(notes(ns), exist_ok=True)

    # 复制本单元分析要用的只读输入(SYMBOLS / MAP*),让宪法的 work/R/... 路径成立
    for fn in os.listdir(work(repo)):
        if fn == "PROGRESS.md" or fn == "shards.json" or fn.startswith("."):
            continue
        src = os.path.join(work(repo), fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(work(ns), fn))

    # 写分片 PROGRESS:沿用原 preamble,但 NAME 改成分片名
    out = []
    for l in header:
        if l.startswith("NAME:"):
            out.append(f"NAME: {ns}")
        elif l.startswith("# "):
            out.append(re.sub(r"—.*$", f"— {ns}", l) if "—" in l else l)
        else:
            out.append(l)
    out += rows
    open(progress(ns), "w", encoding="utf-8").write("\n".join(out) + "\n")


def _namespaces(repo):
    if os.path.exists(manifest_path(repo)):
        return json.load(open(manifest_path(repo), encoding="utf-8"))["shards"]
    # 兜底:扫目录
    base = os.path.join(KIT, "work")
    return sorted(d for d in os.listdir(base)
                  if d.startswith(f"{repo}__s") and os.path.isdir(os.path.join(base, d)))


def cmd_status(repo):
    total = {s: 0 for s in STATUSES}
    for ns in _namespaces(repo):
        if not os.path.exists(progress(ns)):
            continue
        _, data = parse_progress(open(progress(ns), encoding="utf-8").read())
        cnt = {s: sum(1 for r in data if row_status(r) == s) for s in STATUSES}
        for s in STATUSES:
            total[s] += cnt[s]
        print(f"  {ns:16s} TODO={cnt['TODO']:4d} IN_PROGRESS={cnt['IN_PROGRESS']:3d} "
              f"DONE={cnt['DONE']:4d} SKIP={cnt['SKIP']:3d} ERROR={cnt['ERROR']:3d}")
    print(f"  {'合计':16s} TODO={total['TODO']:4d} IN_PROGRESS={total['IN_PROGRESS']:3d} "
          f"DONE={total['DONE']:4d} SKIP={total['SKIP']:3d} ERROR={total['ERROR']:3d}")


def _append_csv(src, dst):
    """把 src 的数据行追加到 dst;若 dst 不存在则连表头一起拷;否则跳过 src 表头。"""
    if not os.path.exists(src):
        return 0
    lines = open(src, encoding="utf-8").read().splitlines()
    if not lines:
        return 0
    first = not os.path.exists(dst)
    with open(dst, "a", encoding="utf-8") as f:
        body = lines if first else lines[1:]   # 非首次跳过表头
        for l in body:
            f.write(l + "\n")
    return max(0, len(lines) - (0 if first else 1))


def cmd_merge(repo):
    os.makedirs(work(repo), exist_ok=True)
    os.makedirs(evidence(repo), exist_ok=True)
    os.makedirs(notes(repo), exist_ok=True)

    # 1) 合并 PROGRESS:用各分片的行状态更新主表(按 ID 覆盖)
    if os.path.exists(progress(repo)):
        header, data = parse_progress(open(progress(repo), encoding="utf-8").read())
        by_id = {row_id(r): i for i, r in enumerate(data)}
        updated = 0
        for ns in _namespaces(repo):
            if not os.path.exists(progress(ns)):
                continue
            _, sdata = parse_progress(open(progress(ns), encoding="utf-8").read())
            for r in sdata:
                rid = row_id(r)
                if rid in by_id:
                    data[by_id[rid]] = r
                    updated += 1
        open(progress(repo), "w", encoding="utf-8").write("\n".join(header + data) + "\n")
        print(f"PROGRESS:回填 {updated} 行状态")

    # 2) 合并 evidence(csv 智能去重表头;md / 其它直接拼接)
    seen = {}
    for ns in _namespaces(repo):
        ev = evidence(ns)
        if not os.path.isdir(ev):
            continue
        for root, _, files in os.walk(ev):
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), ev)
                src = os.path.join(ev, rel)
                dst = os.path.join(evidence(repo), rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if fn.endswith(".csv"):
                    seen[rel] = seen.get(rel, 0) + _append_csv(src, dst)
                else:
                    with open(dst, "a", encoding="utf-8") as f:
                        f.write(open(src, encoding="utf-8").read().rstrip() + "\n\n")
    for rel, n in seen.items():
        print(f"evidence:{rel} 追加 {n} 行")

    # 3) 合并 notes(逐文件搬过去,重名加分片后缀)
    moved = 0
    for ns in _namespaces(repo):
        nd = notes(ns)
        if not os.path.isdir(nd):
            continue
        for fn in os.listdir(nd):
            src = os.path.join(nd, fn)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(notes(repo), fn)
            if os.path.exists(dst):
                stem, ext = os.path.splitext(fn)
                dst = os.path.join(notes(repo), f"{stem}.{ns}{ext}")
            shutil.copy2(src, dst)
            moved += 1
    print(f"notes:搬运 {moved} 个文件")
    print("合并完成。确认无误后可 `clean` 清掉分片目录。")


def cmd_clean(repo):
    for ns in _namespaces(repo):
        for d in (work(ns), evidence(ns), notes(ns)):
            if os.path.isdir(d):
                shutil.rmtree(d)
                print(f"删除 {d}")
    if os.path.exists(manifest_path(repo)):
        os.remove(manifest_path(repo))
    print("分片目录已清理(主仓库 work/evidence/notes 保留)。")


def main():
    ap = argparse.ArgumentParser(description="PROGRESS 队列分片 / 合并工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("split", "status", "merge", "clean"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True)
        if name == "split":
            p.add_argument("--shards", type=int, default=5)
    args = ap.parse_args()

    if args.cmd == "split":
        if args.shards < 1:
            sys.exit("--shards 至少 1")
        print(f"切分 {args.repo} → {args.shards} 片:")
        cmd_split(args.repo, args.shards)
    elif args.cmd == "status":
        cmd_status(args.repo)
    elif args.cmd == "merge":
        cmd_merge(args.repo)
    elif args.cmd == "clean":
        cmd_clean(args.repo)


if __name__ == "__main__":
    main()
