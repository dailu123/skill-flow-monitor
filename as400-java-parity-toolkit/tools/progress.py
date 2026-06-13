"""progress.py — 按"产物文件是否存在 + schema 是否通过"自动统计进度。

不读手动 status,避免 10 人状态打架。判定规则:
  - 某 assignment 行的 artifact 文件存在 且 通过 schema 校验 -> done
  - 文件存在但 schema 不过 -> invalid(需修)
  - 文件不存在 -> todo

输出:
  - 每人进度 + 全局进度到 stdout
  - 刷新 analysis/PROGRESS.md(可提交,作为人读看板)

用法:
  python tools/progress.py --assignments analysis/assignments --out analysis/PROGRESS.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

from _common import info
from validate_outputs import validate_file, infer_schema

ROOT = Path(__file__).resolve().parent.parent


def status_of(artifact: str) -> str:
    if not artifact:
        return "todo"
    fp = ROOT / artifact
    if not fp.exists():
        return "todo"
    sname = infer_schema(fp)
    if not sname:
        return "done"  # 无法判 schema 的产物,只按存在算
    errs = validate_file(fp, sname)
    return "done" if not errs else "invalid"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assignments", default="analysis/assignments")
    ap.add_argument("--out", default="analysis/PROGRESS.md")
    args = ap.parse_args()

    adir = Path(args.assignments)
    rows_per_person: dict[str, dict] = {}
    g_done = g_todo = g_invalid = 0

    for csvf in sorted(adir.glob("*.csv")):
        name = csvf.stem
        with csvf.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        done = todo = invalid = 0
        for r in rows:
            st = status_of(r.get("artifact", ""))
            done += st == "done"
            todo += st == "todo"
            invalid += st == "invalid"
        rows_per_person[name] = {"total": len(rows), "done": done, "todo": todo, "invalid": invalid}
        g_done += done
        g_todo += todo
        g_invalid += invalid

    g_total = g_done + g_todo + g_invalid
    pct = (100.0 * g_done / g_total) if g_total else 0.0

    # 刷新 PROGRESS.md
    lines = [
        "# 进度看板 (PROGRESS)",
        "",
        f"_自动生成于 {dt.datetime.now().isoformat(timespec='seconds')};进度按产物文件存在性 + schema 校验判定,勿手改。_",
        "",
        f"**全局: {g_done}/{g_total} done ({pct:.1f}%)  · todo={g_todo} · invalid={g_invalid}**",
        "",
        "| 成员 | 总数 | done | todo | invalid |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in sorted(rows_per_person):
        s = rows_per_person[name]
        lines.append(f"| {name} | {s['total']} | {s['done']} | {s['todo']} | {s['invalid']} |")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # stdout
    print(f"全局: {g_done}/{g_total} done ({pct:.1f}%)  todo={g_todo} invalid={g_invalid}")
    for name in sorted(rows_per_person):
        s = rows_per_person[name]
        print(f"  {name:<16} done={s['done']:>3} todo={s['todo']:>3} invalid={s['invalid']:>3}")
    if g_invalid:
        print(f"\n⚠ 有 {g_invalid} 个产物未通过 schema,不计入 done。先 python tools/validate_outputs.py 查看。")
    info(f"PROGRESS 刷新 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
