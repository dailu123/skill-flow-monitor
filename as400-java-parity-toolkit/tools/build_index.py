"""build_index.py — 用语义产物构建"代码地图"反向索引(每侧一份独立产物)。

这就是"递推索引 -> 下钻代码"的索引层:先查 JSON(便宜、结构化),
需要确切逻辑时再顺着 path 打开源码。

输入:analysis/semantics/*.json(锚点 + reads_writes)
输出:analysis/index.<side>.json(符合 index.schema.json),含:
  - by_table:   表 -> 引用它的单元
  - by_field:   字段 -> 单元
  - by_call:    调用目标 -> 调用方单元
  - call_graph: [{from_unit, to}]
  - units:      每单元一行(unit_id/path/tables/programs/confidence/needs_human_review)

用法:
  python tools/build_index.py --semantics analysis/semantics --out analysis
  # 生成 analysis/index.as400.json 与 analysis/index.java.json
"""
from __future__ import annotations

import argparse
import datetime as dt
from collections import defaultdict
from pathlib import Path

from _common import read_json, write_json, info


def build_side(units: list[dict]) -> dict:
    by_table: dict[str, set] = defaultdict(set)
    by_field: dict[str, set] = defaultdict(set)
    by_call: dict[str, set] = defaultdict(set)
    call_graph: list[dict] = []
    unit_rows = []

    for s in units:
        uid = s.get("unit_id", "")
        a = s.get("anchors", {})
        tables = sorted(set(a.get("tables", [])) | set(a.get("sql_tables", [])))
        for t in tables:
            by_table[t].add(uid)
        for fld in a.get("fields", []):
            by_field[fld].add(uid)
        for tgt in a.get("call_targets", []):
            by_call[tgt].add(uid)
            call_graph.append({"from_unit": uid, "to": tgt})
        unit_rows.append({
            "unit_id": uid,
            "path": s.get("path", ""),
            "tables": tables,
            "programs": a.get("programs", []),
            "confidence": s.get("confidence", 0),
            "needs_human_review": bool(s.get("needs_human_review", False)),
        })

    def freeze(d: dict[str, set]) -> dict[str, list]:
        return {k: sorted(v) for k, v in sorted(d.items())}

    return {
        "by_table": freeze(by_table),
        "by_field": freeze(by_field),
        "by_call": freeze(by_call),
        "call_graph": call_graph,
        "units": sorted(unit_rows, key=lambda r: r["unit_id"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semantics", default="analysis/semantics")
    ap.add_argument("--out", default="analysis", help="输出目录;生成 index.<side>.json")
    args = ap.parse_args()

    sem_dir = Path(args.semantics)
    by_side: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(sem_dir.glob("*.json")):
        s = read_json(f)
        by_side[s.get("side", "unknown")].append(s)

    out_dir = Path(args.out)
    for side, units in by_side.items():
        idx = build_side(units)
        idx["side"] = side
        idx["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        idx["unit_count"] = len(units)
        out_path = out_dir / f"index.{side}.json"
        write_json(out_path, idx)
        info(f"[{side}] 索引: {len(units)} 单元, {len(idx['by_table'])} 表, "
             f"{len(idx['by_call'])} 调用目标 -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
