"""verify_semantics.py — 用确定性锚点给 LLM 语义产物对账(查 AI 对不对)。

思路:LLM 抽的"语义/规则"是模糊的、会幻觉;但"这个单元引用了哪些表/调用了谁"
是能确定性查的。拿确定性锚点(ingest_ibmi_metadata / ingest_java_anchors / 编译器 *XREF)
当 oracle,反过来给 LLM 的 `anchors` 与 `reads_writes` 判分:
  - 幻觉 (hallucination):LLM 写了、确定性来源里没有的表/调用 -> 可疑(可能编的)。
  - 漏抽 (omission):确定性来源里有、LLM 没写 -> 召回不足。
  - 无法核对 (unverifiable):该单元没有确定性锚点记录。

权威度:确定性来源是 ibmi-outfile / java-parser -> 失配是强信号;
是 regex-best-effort -> 仅供参考(只读不判)。

表/调用是可靠锚点 -> 参与判定;字段命名两侧差异大(如 ORD_AMT vs ordAmt)-> 仅参考。

输出 analysis/qa/<side>.verify.json(符合 anchor-verify.schema.json)+ stdout 摘要。

用法:
  python tools/verify_semantics.py --semantics analysis/semantics \
      --anchors analysis/anchors.as400.json analysis/anchors.java.json \
      --out analysis/qa
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from _common import read_json, write_json, info

AUTHORITATIVE = {"ibmi-outfile", "java-parser", "compiler-xref"}


def norm(s: str) -> str:
    return s.strip().upper()


def load_anchor_index(anchor_files: list[str]) -> dict[str, dict]:
    """path -> {anchors, extractor, side}。"""
    idx: dict[str, dict] = {}
    for f in anchor_files:
        data = read_json(Path(f))
        for r in data.get("records", []):
            idx[r["path"]] = {
                "anchors": r["anchors"],
                "extractor": r.get("extractor", "unknown"),
                "side": r.get("side", data.get("side")),
            }
    return idx


def verify_unit(sem: dict, det: dict | None) -> dict:
    unit_id = sem.get("unit_id", "")
    path = sem.get("path", "")
    if det is None:
        return {
            "unit_id": unit_id, "path": path, "status": "unverifiable",
            "authority": "none",
            "hallucinated": {"tables": [], "call_targets": [], "sql_tables": []},
            "missed": {"tables": [], "call_targets": [], "sql_tables": []},
            "notes": "无确定性锚点记录,无法核对(建议补 DSPPGMREF/java-parser 锚点)。",
        }

    extractor = det["extractor"]
    authority = "authoritative" if extractor in AUTHORITATIVE else "advisory"
    a_llm = sem.get("anchors", {})
    a_det = det["anchors"]

    def union_tables(a: dict) -> set:
        # 把原生表与 SQL 表合并比较:确定性来源(如 DSPPGMREF)区分不了访问方式,
        # 强行分 native/sql 会制造假阳性。比"表的并集"才稳。
        return {norm(x) for x in a.get("tables", [])} | {norm(x) for x in a.get("sql_tables", [])}

    llm_tables = union_tables(a_llm)
    det_tables = union_tables(a_det)
    # reads_writes 里的表也并进 LLM 侧表集合
    llm_tables |= {norm(x.get("table", "")) for x in sem.get("reads_writes", []) if x.get("table")}

    hall_t = sorted(llm_tables - det_tables)
    miss_t = sorted(det_tables - llm_tables)

    llm_calls = {norm(x) for x in a_llm.get("call_targets", [])}
    det_calls = {norm(x) for x in a_det.get("call_targets", [])}
    hall_c = sorted(llm_calls - det_calls)
    miss_c = sorted(det_calls - llm_calls)

    # sql_tables 不单独判(已并入 tables);保留键以符合 schema。
    hallucinated = {"tables": hall_t, "call_targets": hall_c, "sql_tables": []}
    missed = {"tables": miss_t, "call_targets": miss_c, "sql_tables": []}

    any_hall = any(hallucinated.values())
    any_miss = any(missed.values())
    if authority == "authoritative" and any_hall:
        status = "suspect"          # 权威来源里没有却被 LLM 写出 -> 重点复核
    elif any_hall or any_miss:
        status = "review"
    else:
        status = "ok"

    notes = []
    if any_hall:
        notes.append("LLM 引用了确定性来源中不存在的锚点(疑似幻觉)。")
    if any_miss:
        notes.append("确定性来源中存在但 LLM 漏抽的锚点(召回不足)。")
    if authority == "advisory":
        notes.append("确定性来源为 best-effort,本结论仅供参考。")

    return {
        "unit_id": unit_id, "path": path, "status": status, "authority": authority,
        "hallucinated": hallucinated, "missed": missed,
        "notes": " ".join(notes) or "锚点与确定性来源一致。",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--semantics", default="analysis/semantics")
    ap.add_argument("--anchors", nargs="+", required=True, help="一个或多个 anchors.*.json")
    ap.add_argument("--out", default="analysis/qa")
    args = ap.parse_args()

    anchor_idx = load_anchor_index(args.anchors)
    sem_dir = Path(args.semantics)

    by_side: dict[str, list[dict]] = {}
    for f in sorted(sem_dir.glob("*.json")):
        sem = read_json(f)
        side = sem.get("side", "unknown")
        det = anchor_idx.get(sem.get("path", ""))
        by_side.setdefault(side, []).append(verify_unit(sem, det))

    out_dir = Path(args.out)
    rc = 0
    for side, units in by_side.items():
        summary = {
            "units": len(units),
            "ok": sum(u["status"] == "ok" for u in units),
            "review": sum(u["status"] == "review" for u in units),
            "suspect": sum(u["status"] == "suspect" for u in units),
            "unverifiable": sum(u["status"] == "unverifiable" for u in units),
            "hallucinated_total": sum(sum(len(v) for v in u["hallucinated"].values()) for u in units),
            "missed_total": sum(sum(len(v) for v in u["missed"].values()) for u in units),
        }
        report = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "side": side,
            "summary": summary,
            "units": units,
        }
        out_path = out_dir / f"{side}.verify.json"
        write_json(out_path, report)
        print(f"[{side}] units={summary['units']} ok={summary['ok']} review={summary['review']} "
              f"suspect={summary['suspect']} unverifiable={summary['unverifiable']} "
              f"| 幻觉={summary['hallucinated_total']} 漏抽={summary['missed_total']} -> {out_path}")
        for u in units:
            if u["status"] in ("suspect", "review"):
                h = u["hallucinated"]; m = u["missed"]
                if any(h.values()):
                    print(f"   ⚠ {u['unit_id']} 幻觉: tables={h['tables']} calls={h['call_targets']}")
                if any(m.values()):
                    print(f"   · {u['unit_id']} 漏抽: tables={m['tables']} calls={m['call_targets']}")
        if summary["suspect"]:
            rc = 1  # 有权威来源戳穿的幻觉 -> 非零退出,便于 CI 卡住

    info("verify 完成")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
