"""import_runtime_diffs.py — 导入已有运行时差异(diff)证据,归一化备用。

很多迁移项目已有"双跑"对比产物(同输入喂 AS400 与 Java,记录输出/库差异)。
本脚本把这些 CSV/JSON 归一为统一结构,供 aggregate_matrix.py 交叉核对:
高亮"语义说相同、运行时说不同"的对。

输入 CSV 约定列(缺列容忍):
  mapping_id, test_id, case_id, field, as400_value, java_value, equal(0/1)

用法:
  python tools/import_runtime_diffs.py --in runtime_dumps/ --out analysis/runtime_diffs.json
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from _common import iter_files, read_json, write_json, info, warn


def from_csv(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            equal_raw = (r.get("equal") or "").strip().lower()
            equal = equal_raw in ("1", "true", "yes", "y")
            rows.append({
                "mapping_id": r.get("mapping_id", "").strip(),
                "test_id": r.get("test_id", "").strip(),
                "case_id": r.get("case_id", "").strip(),
                "field": r.get("field", "").strip(),
                "as400_value": r.get("as400_value", ""),
                "java_value": r.get("java_value", ""),
                "equal": equal,
                "source": path.name,
            })
    return rows


def from_json(path: Path) -> list[dict]:
    data = read_json(path)
    items = data if isinstance(data, list) else data.get("diffs", [])
    out = []
    for r in items:
        out.append({
            "mapping_id": r.get("mapping_id", ""),
            "test_id": r.get("test_id", ""),
            "case_id": r.get("case_id", ""),
            "field": r.get("field", ""),
            "as400_value": r.get("as400_value", ""),
            "java_value": r.get("java_value", ""),
            "equal": bool(r.get("equal", False)),
            "source": path.name,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="indir", required=True, help="运行时 diff 目录(csv/json)")
    ap.add_argument("--out", default="analysis/runtime_diffs.json")
    args = ap.parse_args()

    root = Path(args.indir)
    if not root.exists():
        warn(f"输入目录不存在: {root}")
        return 2

    rows: list[dict] = []
    for p in iter_files(root, [".csv"]):
        rows.extend(from_csv(p))
    for p in iter_files(root, [".json"]):
        rows.extend(from_json(p))

    # 按 mapping 汇总:是否存在不相等的运行时字段。
    by_mapping: dict[str, dict] = {}
    for r in rows:
        m = r["mapping_id"] or "(unknown)"
        agg = by_mapping.setdefault(m, {"mapping_id": m, "cases": 0, "mismatches": 0, "fields": []})
        agg["cases"] += 1
        if not r["equal"]:
            agg["mismatches"] += 1
            if r["field"] and r["field"] not in agg["fields"]:
                agg["fields"].append(r["field"])

    out = {
        "total_rows": len(rows),
        "mappings_with_runtime_evidence": len(by_mapping),
        "by_mapping": list(by_mapping.values()),
        "rows": rows,
    }
    write_json(Path(args.out), out)
    info(f"运行时 diff 导入: {len(rows)} 行, {len(by_mapping)} 个 mapping -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
