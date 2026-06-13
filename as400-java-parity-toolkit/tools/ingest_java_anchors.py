"""ingest_java_anchors.py — 把 Java 解析器(JavaParser/JSqlParser)的中间产物
归一为标准 anchors.java.json,喂给 build_units.py。

为什么不在 Python 里解析 Java?因为最准的 Java 锚点来自**真正的 AST 解析器**
(JavaParser/Spoon)+ SQL 解析器(JSqlParser),它们是 Java 生态的开源库。
本仓库的 `java-extractor/`(Maven 项目)用它们产出一份**中间 JSON**,
本脚本只负责把中间 JSON 归一成本工具链统一的 anchors 格式。

中间 JSON 契约(java-extractor 产出):
{
  "tool": "java-extractor",
  "version": "1.0",
  "source_root": "samples/java",
  "units": [
    {
      "path": "samples/java/DiscountService.java",
      "class": "com.example.order.DiscountService",
      "methods": ["calcDiscount"],
      "calls": ["CustomerRepo.findById", "OrderHeaderRepo.update"],
      "jpa_tables": ["ORDHDR", "CUSTMAS"],
      "jpa_columns": ["ORD_AMT", "DISC_AMT"],
      "sql_tables": ["CUSTMAS"],
      "sql_columns": ["CUST_NO"],
      "endpoints": ["/customer/search"],
      "mybatis_tables": []
    }
  ]
}

用法:
  python tools/ingest_java_anchors.py --in java-extractor/out/java-anchors.raw.json --out analysis/anchors.java.json
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import read_json, write_json, info, warn


def short_class(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1] if fqcn else ""


def to_anchors(u: dict) -> dict:
    jpa_tables = u.get("jpa_tables", []) or []
    sql_tables = u.get("sql_tables", []) or []
    mybatis_tables = u.get("mybatis_tables", []) or []
    tables = sorted(set(jpa_tables) | set(sql_tables) | set(mybatis_tables))
    fields = sorted(set(u.get("jpa_columns", []) or []) | set(u.get("sql_columns", []) or []))
    return {
        "tables": tables,
        "fields": fields,
        "programs": [short_class(u.get("class", "")) or Path(u.get("path", "x")).stem],
        "transactions": [],
        "screens": sorted(set(u.get("endpoints", []) or [])),
        "call_targets": sorted(set(u.get("calls", []) or [])),
        "sql_tables": sorted(set(sql_tables) | set(mybatis_tables)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="infile", required=True, help="java-extractor 产出的中间 JSON")
    ap.add_argument("--out", default="analysis/anchors.java.json")
    args = ap.parse_args()

    data = read_json(Path(args.infile))
    if data.get("tool") != "java-extractor":
        warn(f"输入 tool 字段不是 java-extractor(实为 {data.get('tool')!r}),仍尝试解析。")

    records = []
    for u in data.get("units", []):
        path = u.get("path")
        if not path:
            warn(f"跳过缺 path 的单元: {u.get('class')}")
            continue
        records.append({
            "path": path,
            "side": "java",
            "anchors": to_anchors(u),
            # 来自真正的 AST/SQL 解析器,权威。
            "anchor_confidence": 0.95,
            "extractor": "java-parser",
            "needs_authoritative_tool": False,
        })

    out = {
        "side": "java",
        "source_root": data.get("source_root", ""),
        "file_count": len(records),
        "extracted": len(records),
        "skipped_non_utf8": 0,
        "disclaimer": "来自 JavaParser/JSqlParser 的 AST 解析,锚点准确;LLM 语义仍需 verify_semantics 对账。",
        "records": records,
    }
    write_json(Path(args.out), out)
    info(f"Java 锚点归一完成: {len(records)} 个单元 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
