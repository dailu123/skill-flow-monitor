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
KIT_REL = os.path.basename(KIT)  # 仓库根下 kit 目录名,用于咒语里的相对路径
STATUSES = ("TODO", "IN_PROGRESS", "DONE", "SKIP", "ERROR")

# 每个命名空间的"咒语":在 Copilot agent 里新开会话粘贴这段,它会按宪法把这片所有 TODO 跑完。
SPELL = (
    "本轮仓库 R = {ns}。读取 {kit}/dot-github/copilot-instructions.md（操作宪法）和 "
    "{kit}/work/{ns}/PROGRESS.md。宪法里所有 work/R、evidence/R、notes/R 路径中的 R "
    "一律用 {ns}。严格按宪法的 LOOP PROTOCOL 连续处理 PROGRESS.md 里的每一个 TODO 单元，"
    "直到没有 TODO 为止：每个单元完成就把该行改成 DONE 并按宪法追加证据 / 写笔记。"
    "不要问我、不要等待、不要写超过三句总结、跳过第7步可视化刷新。"
)
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


def _append_csv(src, dst, dry=False):
    """把 src 的数据行追加到 dst;若 dst 不存在则连表头一起拷;否则跳过 src 表头。返回追加行数。"""
    if not os.path.exists(src):
        return 0
    lines = open(src, encoding="utf-8").read().splitlines()
    if not lines:
        return 0
    first = not os.path.exists(dst)
    body = lines if first else lines[1:]   # 非首次跳过表头
    if not dry:
        with open(dst, "a", encoding="utf-8") as f:
            for l in body:
                f.write(l + "\n")
    return len(body)


def cmd_merge(repo, dry=False):
    tag = "[预览] " if dry else ""
    if not dry:
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
                    if not dry:
                        data[by_id[rid]] = r
                    updated += 1
        if not dry:
            open(progress(repo), "w", encoding="utf-8").write("\n".join(header + data) + "\n")
        print(f"{tag}PROGRESS:回填 {updated} 行状态")

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
                if fn.endswith(".csv"):
                    if not dry:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                    seen[rel] = seen.get(rel, 0) + _append_csv(src, dst, dry)
                else:
                    seen[rel] = seen.get(rel, 0) + 1
                    if not dry:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with open(dst, "a", encoding="utf-8") as f:
                            f.write(open(src, encoding="utf-8").read().rstrip() + "\n\n")
    for rel, n in seen.items():
        print(f"{tag}evidence:{rel} {'追加' if rel.endswith('.csv') else '拼接'} {n} {'行' if rel.endswith('.csv') else '段'}")

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
            if not dry:
                shutil.copy2(src, dst)
            moved += 1
    print(f"{tag}notes:搬运 {moved} 个文件")
    print(f"{tag}" + ("预览结束,未改动任何文件;去掉 --dry-run 才会真正写入。"
                      if dry else "合并完成。确认无误后可 `clean` 清掉分片目录。"))


def _todo_of(ns):
    if not os.path.exists(progress(ns)):
        return 0
    _, data = parse_progress(open(progress(ns), encoding="utf-8").read())
    return sum(1 for r in data if row_status(r) == "TODO")


def cmd_assign(repos_csv, people):
    repos = [r.strip() for r in repos_csv.split(",") if r.strip()]
    all_ns = []
    for r in repos:
        ns = _namespaces(r)
        if not ns:
            sys.exit(f"仓库 {r} 没有分片,先 split。")
        all_ns += ns
    # 轮转分配:第 i 个命名空间给第 (i % people) 个人,跨仓库自然均衡
    buckets = [[] for _ in range(people)]
    for i, ns in enumerate(all_ns):
        buckets[i % people].append(ns)

    out = [f"# 分块任务分配（{people} 人）\n",
           "> 每人:`git pull` → 打开本仓库 → 装 copilot-auto-continue 扩展。",
           "> 对你负责的**每个命名空间**,新开一个 Copilot agent 会话,把对应「咒语」粘贴进去回车;",
           "> 然后点右下角状态栏开启 babysit(它会在 agent 停下时自动发「继续」,你可以去干别的)。",
           "> 跑完后**只提交你自己命名空间的目录**(work/<ns>、evidence/<ns>、notes/<ns>),发 PR。\n"]
    for pi in range(people):
        nss = buckets[pi]
        if not nss:
            continue
        summary = ", ".join(f"{ns}(TODO {_todo_of(ns)})" for ns in nss)
        out.append(f"\n## 第 {pi + 1} 人\n负责:{summary}")
        for ns in nss:
            spell = SPELL.format(ns=ns, kit=KIT_REL)
            out.append(f"\n### 咒语 — {ns}\n```\n{spell}\n```")
    # 给协作者的 Git 提交步骤(各改各文件,合并零冲突)
    egns = buckets[0][0] if buckets and buckets[0] else "hub__s1"
    kit = KIT_REL
    out.append(
        "\n---\n\n## 提交步骤(给协作者)\n"
        "\n你只改自己命名空间的目录,所以和别人**不会冲突**。跑完后:\n"
        "\n```bash\n"
        f"git switch -c work/你的名字           # 开自己的分支\n"
        f"# 只 add 你负责的命名空间目录(每个 ns 三处),例如 {egns}:\n"
        f"git add {kit}/work/{egns} {kit}/evidence/{egns} {kit}/notes/{egns}\n"
        f"git commit -m \"分析 {egns}\"\n"
        f"git push -u origin work/你的名字       # 然后在 GitHub 上发 PR\n"
        "```\n"
        "\n> 注意:**不要** `git add .`,以免带上别人的改动或本地源码;只 add 自己那几个 ns 目录。\n"
        "> 被分析的源码不要提交进本仓库。"
    )

    path_out = os.path.join(KIT, "ASSIGNMENTS.md")
    open(path_out, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"分配表写入 {path_out}")
    for pi in range(people):
        if buckets[pi]:
            print(f"  第 {pi + 1} 人:{', '.join(buckets[pi])}  "
                  f"(TODO 合计 {sum(_todo_of(ns) for ns in buckets[pi])})")


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
        if name == "merge":
            p.add_argument("--dry-run", action="store_true", help="只预览汇总结果,不写任何文件")
    pa = sub.add_parser("assign")
    pa.add_argument("--repos", required=True, help="逗号分隔,如 hub,mca")
    pa.add_argument("--people", type=int, required=True)
    args = ap.parse_args()

    if args.cmd == "split":
        if args.shards < 1:
            sys.exit("--shards 至少 1")
        print(f"切分 {args.repo} → {args.shards} 片:")
        cmd_split(args.repo, args.shards)
    elif args.cmd == "status":
        cmd_status(args.repo)
    elif args.cmd == "merge":
        cmd_merge(args.repo, dry=args.dry_run)
    elif args.cmd == "clean":
        cmd_clean(args.repo)
    elif args.cmd == "assign":
        if args.people < 1:
            sys.exit("--people 至少 1")
        cmd_assign(args.repos, args.people)


if __name__ == "__main__":
    main()
