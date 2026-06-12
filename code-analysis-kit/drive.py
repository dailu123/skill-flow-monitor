#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无人值守驱动器：反复调用 Copilot CLI，每轮让它"处理一小批单元就退出"，
直到 PROGRESS.md 队列清空。解决 Agent 模式"跑几个就停"的问题。

用法（Windows，在仓库根目录）：
  python code-analysis-kit\\drive.py --repo mca
  python code-analysis-kit\\drive.py --repo hub --batch 5 --model gemini-flash

前提：装好 Copilot CLI（终端里 `copilot` 可用）并已登录。
没装的话：npm install -g @github/copilot 或参考 GitHub 文档。

参数：
  --repo      mca | hub（盯哪个队列）
  --batch     每轮让模型处理几个单元（默认 5；小批量=新鲜上下文=质量稳定）
  --profile   copilot | gemini（执行器方言：自动批准/信任目录/模型 的参数名不同）
              没有 Copilot CLI 的话装免费的 Gemini CLI 也能跑：npm install -g @google/gemini-cli
  --cli       覆盖 CLI 命令名（默认随 profile：copilot / gemini）
  --model     传给 CLI 的模型名（可选，省钱用快模型）
  --timeout   单轮超时秒数（默认 2400，超时杀掉进入下一轮）
  --max-runs  最多跑多少轮（默认 999，安全阀）

行为：
  - 每轮开始把遗留的 IN_PROGRESS 重置回 TODO（上一轮崩了的断点自动恢复）
  - 连续 2 轮 TODO 数没变化就报警退出（模型卡住了，人来看）
  - 全程写日志 work/<repo>/driver.log
"""
import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime

KIT = os.path.dirname(os.path.abspath(__file__))


def log(repo, msg):
    line = f"[{datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(os.path.join(KIT, "work", repo, "driver.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def progress_path(repo):
    return os.path.join(KIT, "work", repo, "PROGRESS.md")


def repo_source_root(repo):
    """PROGRESS.md 顶部的 ROOT: 行 = 被分析源码的路径（多半在工作目录之外）。"""
    m = re.search(r"^ROOT:\s*(.+)$", open(progress_path(repo), encoding="utf-8").read(), re.M)
    return m.group(1).strip() if m else None


def count_status(repo):
    txt = open(progress_path(repo), encoding="utf-8").read()
    return {st: len(re.findall(rf"\|\s*{st}\s*\|", txt))
            for st in ("TODO", "IN_PROGRESS", "DONE", "SKIP", "ERROR")}


def reset_stuck(repo):
    """上一轮崩掉留下的 IN_PROGRESS 重置回 TODO（此刻没有 agent 在跑，是安全的）。"""
    p = progress_path(repo)
    txt = open(p, encoding="utf-8").read()
    n = txt.count("| IN_PROGRESS |")
    if n:
        open(p, "w", encoding="utf-8").write(txt.replace("| IN_PROGRESS |", "| TODO |"))
        log(repo, f"恢复 {n} 个上轮遗留的 IN_PROGRESS → TODO")


def make_prompt(repo, batch):
    return (
        f"读取 code-analysis-kit/dot-github/copilot-instructions.md（操作宪法）和 "
        f"code-analysis-kit/work/{repo}/PROGRESS.md。严格按宪法的 LOOP PROTOCOL "
        f"连续处理恰好 {batch} 个 TODO 单元（不足 {batch} 个就处理到队列没有 TODO 为止），"
        f"每个单元完成后立即更新 PROGRESS.md 并追加 evidence CSV。"
        f"处理完这一批就结束本次任务并退出，不要继续，不要提问，不要总结超过三句话。"
        f"跳过 LOOP 第7步的可视化刷新（外部已有 watch 进程）。"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, choices=["mca", "hub"])
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--profile", choices=["copilot", "gemini"], default="copilot")
    ap.add_argument("--cli", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--timeout", type=int, default=2400)
    ap.add_argument("--max-runs", type=int, default=999)
    ap.add_argument("--add-dir", action="append", default=[],
                    help="额外加入 CLI 信任区的目录（可多次）；被分析源码的 ROOT 会自动加入")
    args = ap.parse_args()

    if not os.path.exists(progress_path(args.repo)):
        sys.exit(f"找不到 {progress_path(args.repo)}，先跑 bootstrap.py")

    repo_root = os.path.dirname(KIT)  # kit 在仓库根下，工作目录用仓库根
    stall = 0
    last_todo = -1

    for run in range(1, args.max_runs + 1):
        reset_stuck(args.repo)
        c = count_status(args.repo)
        if c["TODO"] == 0:
            log(args.repo, f"队列清空！DONE={c['DONE']} SKIP={c['SKIP']}，驱动器收工。")
            return
        if c["TODO"] == last_todo:
            stall += 1
            if stall >= 2:
                log(args.repo, f"连续 {stall} 轮 TODO 数({c['TODO']})没变化——模型卡住了，"
                               f"请人工看 driver.log 和最近一轮输出。")
                sys.exit(1)
        else:
            stall = 0
        last_todo = c["TODO"]

        # 不同执行器的参数方言
        prof = {
            "copilot": {"bin": "copilot", "yolo": ["--allow-all-tools"],
                        "dirs": "repeat:--add-dir", "model": "--model"},
            "gemini": {"bin": "gemini", "yolo": ["--yolo"],
                       "dirs": "comma:--include-directories", "model": "-m"},
        }[args.profile]
        cli = (args.cli or prof["bin"]).split()
        cmd = cli + ["-p", make_prompt(args.repo, args.batch)] + prof["yolo"]
        src_root = repo_source_root(args.repo)
        dirs = list(dict.fromkeys(
            ([src_root] if src_root and os.path.isdir(src_root) else []) + args.add_dir))
        if dirs:  # 源码在工作目录之外，必须进信任区，否则 CLI 会卡在目录授权上
            style, flag = prof["dirs"].split(":")
            if style == "repeat":
                for d in dirs:
                    cmd += [flag, d]
            else:
                cmd += [flag, ",".join(dirs)]
        if args.model:
            cmd += [prof["model"], args.model]
        log(args.repo, f"第 {run} 轮：剩 TODO {c['TODO']} / DONE {c['DONE']}，"
                       f"派发 {args.batch} 个单元...")
        try:
            r = subprocess.run(cmd, cwd=repo_root, timeout=args.timeout,
                               stdin=subprocess.DEVNULL,  # 没有人值守：等输入=立即失败，别干耗
                               capture_output=True, text=True, encoding="utf-8", errors="ignore")
            tail = (r.stdout or "").strip().splitlines()[-3:]
            log(args.repo, f"第 {run} 轮结束（exit={r.returncode}）" +
                (("：" + " / ".join(tail)) if tail else ""))
            if r.returncode != 0 and r.stderr:
                log(args.repo, f"stderr: {r.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            log(args.repo, f"第 {run} 轮超时（{args.timeout}s）已杀掉，断点会在下轮恢复。")
        except FileNotFoundError:
            sys.exit(f"找不到命令 {cli[0]!r}。安装其一：Copilot CLI（npm install -g @github/copilot）"
                     f"或 Gemini CLI（npm install -g @google/gemini-cli，免费），"
                     f"或用 --cli 指定你的 agent 命令。")
        time.sleep(3)

    log(args.repo, f"达到 --max-runs={args.max_runs} 上限，驱动器退出。")


if __name__ == "__main__":
    main()
