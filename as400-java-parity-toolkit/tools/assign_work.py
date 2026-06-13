"""assign_work.py — 把 units.csv 均衡分给 N 个人,产出 assignments/<name>.csv。

均衡目标:每人 est_tokens 总量尽量相近,同时高风险单元尽量分散(不堆在一人)。
做法:按风险优先 + est_tokens 降序,用"最小负载优先"贪心装箱。

assignments/<name>.csv 列:
  unit_id, side, path, risk, est_tokens, prompt, status, artifact
  - status 初始 todo;成员完成后由 progress.py 依"产物文件是否存在"自动判 done,
    尽量不手动改,避免 10 人状态打架。
  - artifact 是约定产出路径(成员把 JSON 写到这里)。

用法:
  python tools/assign_work.py --units analysis/units.csv --people names.txt --out analysis/assignments
  # names.txt 每行一个成员名;或用 --names a,b,c
"""
from __future__ import annotations

import argparse
import csv
import heapq
from pathlib import Path

from _common import info

ARTIFACT_DIR = {
    # 第一步产物是语义抽取;后续步骤(mapping/diff/test)由协调人按阶段再分配。
    "/extract-semantics": "analysis/semantics",
}


def artifact_path(unit_id: str, prompt: str) -> str:
    base = ARTIFACT_DIR.get(prompt.strip(), "analysis/semantics")
    return f"{base}/{unit_id}.json"


def load_units(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_people(args) -> list[str]:
    if args.names:
        return [n.strip() for n in args.names.split(",") if n.strip()]
    people = []
    with Path(args.people).open("r", encoding="utf-8") as f:
        for line in f:
            n = line.strip()
            if n and not n.startswith("#"):
                people.append(n)
    return people


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--units", default="analysis/units.csv")
    ap.add_argument("--people", help="每行一个成员名的文件")
    ap.add_argument("--names", help="逗号分隔成员名,优先于 --people")
    ap.add_argument("--out", default="analysis/assignments")
    args = ap.parse_args()

    if not args.people and not args.names:
        ap.error("需提供 --people 或 --names")

    units = load_units(Path(args.units))
    people = load_people(args)
    if not people:
        ap.error("成员列表为空")

    # 风险优先 + token 降序,保证大/高风险单元先入箱、被分散。
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    units.sort(key=lambda u: (risk_order.get(u["risk"], 9), -int(u["est_tokens"])))

    # 最小负载优先堆:(累计 tokens, 累计高风险数, 人名索引)
    heap = [(0, 0, i) for i in range(len(people))]
    heapq.heapify(heap)
    buckets: dict[str, list[dict]] = {p: [] for p in people}

    for u in units:
        load, hi, idx = heapq.heappop(heap)
        name = people[idx]
        u2 = dict(u)
        u2["status"] = "todo"
        u2["artifact"] = artifact_path(u["unit_id"], u.get("prompt", "/extract-semantics"))
        buckets[name].append(u2)
        is_hi = 1 if u["risk"] in ("critical", "high") else 0
        # 高风险计入次级权重,促使其分散
        heapq.heappush(heap, (load + int(u["est_tokens"]) + is_hi * 300, hi + is_hi, idx))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["unit_id", "side", "path", "risk", "est_tokens", "prompt", "status", "artifact"]
    for name, rows in buckets.items():
        fp = out_dir / f"{name}.csv"
        with fp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})
        total = sum(int(r["est_tokens"]) for r in rows)
        info(f"{name}: {len(rows)} 单元, ~{total} tokens -> {fp}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
