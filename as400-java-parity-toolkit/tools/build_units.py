"""build_units.py — 把两侧锚点切成分析单元清单 units.csv。

输入:extract_anchors.py(或专业工具转换后)产出的 anchors.*.json。
输出:units.csv,列:
  side, unit_id, path, risk, est_tokens, prompt
  - unit_id 稳定且唯一(side + 序号 + 文件 stem)。
  - risk 由启发式打分(命中核心表/事务/SQL 多 -> 高)。
  - est_tokens 粗估,用于分配均衡与模型选择。
  - prompt 建议在 Copilot agent 里跑的 / 命令(extract-semantics)。

用法:
  python tools/build_units.py --anchors analysis/anchors.as400.json analysis/anchors.java.json --out analysis/units.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from _common import read_json, info

# 高风险锚点关键词(命中则抬高 risk)。可按项目核心域调整。
HIGH_RISK_TABLE_HINTS = ("ACCT", "LEDGER", "GL", "TXN", "POST", "BAL", "AUDIT", "PAY")


def est_tokens(anchors: dict) -> int:
    """粗估单元规模:锚点越多越大。仅用于均衡与模型选择,非精确。"""
    n = sum(len(v) for v in anchors.values())
    return 500 + n * 80


def score_risk(anchors: dict) -> str:
    score = 0
    blob = " ".join(
        x for v in (anchors.get("tables", []), anchors.get("sql_tables", []), anchors.get("transactions", []))
        for x in v
    ).upper()
    for hint in HIGH_RISK_TABLE_HINTS:
        if hint in blob:
            score += 2
    # 写操作侧、SQL 多、事务码存在 -> 抬高
    score += min(len(anchors.get("sql_tables", [])), 3)
    score += min(len(anchors.get("transactions", [])), 2)
    score += min(len(anchors.get("screens", [])), 1)
    if score >= 6:
        return "critical"
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def load_records(anchor_files: list[str]) -> list[dict]:
    recs = []
    for f in anchor_files:
        data = read_json(Path(f))
        side = data["side"]
        for i, r in enumerate(data["records"], start=1):
            stem = Path(r["path"]).stem
            unit_id = f"{side[:3].upper()}-{i:04d}-{stem}"
            recs.append({
                "side": side,
                "unit_id": unit_id,
                "path": r["path"],
                "risk": score_risk(r["anchors"]),
                "est_tokens": est_tokens(r["anchors"]),
                # extract-semantics 是显式入口;agent 模式里手动 / 触发。
                "prompt": "/extract-semantics",
            })
    return recs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anchors", nargs="+", required=True, help="一个或多个 anchors.*.json")
    ap.add_argument("--out", default="analysis/units.csv")
    args = ap.parse_args()

    recs = load_records(args.anchors)
    # 风险优先排序,便于后续把高风险单元先分给强模型/资深成员。
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recs.sort(key=lambda r: (risk_order[r["risk"]], -r["est_tokens"]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["side", "unit_id", "path", "risk", "est_tokens", "prompt"])
        w.writeheader()
        w.writerows(recs)

    info(f"units 生成: {len(recs)} 个单元 -> {out}")
    info("风险分布: " + ", ".join(f"{k}={sum(1 for r in recs if r['risk']==k)}" for k in risk_order))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
