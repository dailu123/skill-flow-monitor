"""aggregate_matrix.py — 汇总对等性矩阵 + 覆盖率 + 分类风险点 N/M。

输入(均为 agent 产物 + 可选运行时证据):
  analysis/mapping/*.json    对齐结果
  analysis/diffs/*.json      规则级 diff
  analysis/runtime_diffs.json (可选) import_runtime_diffs.py 产出

输出:
  analysis/parity_matrix.json  (符合 schemas/parity-matrix.schema.json)
  并在 stdout 打印人读摘要:
    - 单侧桶计数(matched / as400_only / java_only)
    - 每缺陷类"分类风险点 N / 已验 M"
    - 高亮"语义说相同、运行时说不同"的对

用法:
  python tools/aggregate_matrix.py --analysis analysis --out analysis/parity_matrix.json
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from _common import read_json, write_json, info, warn


def load_dir(p: Path) -> list[dict]:
    out = []
    if not p.exists():
        return out
    for f in sorted(p.glob("*.json")):
        try:
            out.append(read_json(f))
        except Exception as e:  # noqa: BLE001
            warn(f"跳过无法读取的 {f}: {e}")
    return out


def risk_from_defects(open_classes: set[str]) -> str:
    critical = {"packed-zoned-precision", "transaction-commit-boundary", "logical-delete"}
    if open_classes & critical:
        return "critical"
    if open_classes:
        return "high"
    return "low"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", default="analysis")
    ap.add_argument("--out", default="analysis/parity_matrix.json")
    args = ap.parse_args()

    base = Path(args.analysis)
    mappings = load_dir(base / "mapping")
    diffs = load_dir(base / "diffs")

    runtime_path = base / "runtime_diffs.json"
    runtime = read_json(runtime_path) if runtime_path.exists() else {"by_mapping": []}
    runtime_mismatch = {
        m["mapping_id"]: m["mismatches"] for m in runtime.get("by_mapping", []) if m.get("mismatches", 0) > 0
    }

    # 桶计数
    buckets = {"matched": 0, "as400_only": 0, "java_only": 0}
    function_by_mapping: dict[str, str] = {}
    for m in mappings:
        b = m.get("bucket")
        if b in buckets:
            buckets[b] += 1
        function_by_mapping[m.get("mapping_id", "")] = m.get("business_function", m.get("mapping_id", "(unnamed)"))

    # diff 按 mapping 归并
    diff_by_mapping: dict[str, dict] = {}
    defect_rollup: dict[str, dict] = {}
    total_rules = 0
    total_need_rt = 0
    total_rt_verified = 0

    for d in diffs:
        mid = d.get("mapping_id", "")
        agg = diff_by_mapping.setdefault(mid, {
            "verdict": d.get("pair_verdict", "uncertain"),
            "rules_total": 0, "rules_runtime_verified": 0, "open_classes": set(),
        })
        for r in d.get("rules", []):
            total_rules += 1
            agg["rules_total"] += 1
            dc = r.get("defect_class", "none")
            if dc and dc != "none":
                roll = defect_rollup.setdefault(dc, {"defect_class": dc, "risk_points": 0, "verified": 0})
                roll["risk_points"] += 1
                if r.get("verdict") in ("different", "uncertain"):
                    agg["open_classes"].add(dc)
            need_rt = bool(r.get("needs_runtime_test"))
            if need_rt:
                total_need_rt += 1
            # "已验"= 该规则需运行时且其 mapping 有运行时证据
            if need_rt and mid in runtime_mismatch:
                agg["rules_runtime_verified"] += 1
                total_rt_verified += 1
                if dc and dc != "none":
                    defect_rollup[dc]["verified"] += 1

    # functions 行
    functions = []
    semantic_same_runtime_diff = []  # 语义说相同、运行时说不同
    for m in mappings:
        mid = m.get("mapping_id", "")
        fn = function_by_mapping.get(mid, mid)
        if m.get("bucket") == "as400_only":
            functions.append({"business_function": fn, "verification_status": "unmapped",
                              "risk": "high", "coverage": {"rules_total": 0, "rules_runtime_verified": 0},
                              "open_defect_classes": []})
            continue
        if m.get("bucket") == "java_only":
            functions.append({"business_function": fn, "verification_status": "unmapped",
                              "risk": "high", "coverage": {"rules_total": 0, "rules_runtime_verified": 0},
                              "open_defect_classes": []})
            continue
        agg = diff_by_mapping.get(mid)
        if not agg:
            functions.append({"business_function": fn, "verification_status": "not_compared",
                              "risk": "medium", "coverage": {"rules_total": 0, "rules_runtime_verified": 0},
                              "open_defect_classes": []})
            continue
        open_classes = agg["open_classes"]
        status = agg["verdict"]
        functions.append({
            "business_function": fn,
            "verification_status": status,
            "risk": risk_from_defects(open_classes),
            "coverage": {
                "rules_total": agg["rules_total"],
                "rules_runtime_verified": agg["rules_runtime_verified"],
            },
            "open_defect_classes": sorted(open_classes),
        })
        # 交叉核对:pair 语义判 candidate_equivalent 但运行时有不等
        if status == "candidate_equivalent" and mid in runtime_mismatch:
            semantic_same_runtime_diff.append((mid, fn, runtime_mismatch[mid]))

    matrix = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "buckets": buckets,
        "functions": functions,
        "defect_class_rollup": sorted(defect_rollup.values(), key=lambda r: -r["risk_points"]),
        "totals": {
            "mappings": len(mappings),
            "rules": total_rules,
            "rules_needing_runtime": total_need_rt,
            "rules_runtime_verified": total_rt_verified,
        },
    }
    write_json(Path(args.out), matrix)

    # ---- 人读摘要 ----
    print("=" * 56)
    print("对等性矩阵汇总 (parity matrix)")
    print("=" * 56)
    print(f"单侧桶:  matched={buckets['matched']}  "
          f"as400_only(缺失)={buckets['as400_only']}  java_only(新增)={buckets['java_only']}")
    print(f"规则总数={total_rules}  需运行时={total_need_rt}  已运行时验证={total_rt_verified}")
    print("\n分类风险点 (缺陷类: N 命中 / M 已验):")
    if matrix["defect_class_rollup"]:
        for r in matrix["defect_class_rollup"]:
            print(f"  - {r['defect_class']:<32} N={r['risk_points']:>3} / M={r['verified']:>3}")
    else:
        print("  (暂无规则级 diff;先跑 compare-pair)")
    if semantic_same_runtime_diff:
        print("\n⚠ 语义说相同 但 运行时说不同 (最高优先复核):")
        for mid, fn, n in semantic_same_runtime_diff:
            print(f"  - {mid}  {fn}  运行时不等字段/用例={n}")
    print(f"\n矩阵已写出 -> {args.out}")
    info("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
