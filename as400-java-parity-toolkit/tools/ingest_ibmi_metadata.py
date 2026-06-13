"""ingest_ibmi_metadata.py — 把 IBM i 自带命令/编目导出的元数据归一为 anchors.as400.json。

【为什么这是免费且最准的 AS400 锚点来源】
不解析 RPG 源码,而是用 IBM i **平台自带**的交叉引用,它们是权威的、确定性的、免费的:
  - DSPPGMREF (Display Program References):程序引用了哪些文件/程序。
      CL: DSPPGMREF PGM(*ALL/lib) OUTPUT(*OUTFILE) OUTFILE(lib/PGMREF)
      然后把 QADSPPGM 输出文件转 CSV(CPYTOIMPF 或 SQL),映射列:
        WHPNAM -> program, WHFNAM -> referenced_object, WHOBJT -> object_type
  - DSPFFD (Display File Field Description):文件的字段级描述。
      CL: DSPFFD FILE(lib/file) OUTPUT(*OUTFILE) OUTFILE(lib/FFD)
      映射列: WHFILE -> file, WHFLDE -> field
  - DB2 编目(可选): SELECT TABLE_NAME, COLUMN_NAME FROM QSYS2.SYSCOLUMNS ... -> table,column
  - (可选) RPG/COBOL 编译时 OPTION(*XREF) 的交叉引用清单,也可转成同样的 CSV 喂进来。

CSV 用友好列名(导出时把上面的物理字段名映射过来即可)。各文件都可缺省,有什么喂什么。

单元粒度是"程序"。程序的字段锚点 = 它引用的那些文件的字段并集。
若提供 --src,脚本会用程序名去源码目录找同名文件,解析出真实 path(便于和语义产物按 path 对齐);
找不到则用程序名作合成 path。

用法:
  python tools/ingest_ibmi_metadata.py \
      --dsppgmref samples/ibmi_exports/dsppgmref.csv \
      --dspffd    samples/ibmi_exports/dspffd.csv \
      --src samples/as400 \
      --out analysis/anchors.as400.json
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from _common import write_json, info, warn

# DSPPGMREF 的对象类型 -> 归类
FILE_TYPES = {"FILE", "PF", "LF", "*FILE", "PHYSICAL", "LOGICAL"}
PGM_TYPES = {"PGM", "*PGM", "PROGRAM", "SRVPGM", "*SRVPGM"}
DSPF_HINT = {"DSPF", "DISPLAY"}


def read_csv(path: str | None) -> list[dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        warn(f"CSV 不存在,跳过: {p}")
        return []
    with p.open("r", encoding="utf-8", newline="") as f:
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def build_file_fields(ffd_rows: list[dict], db2_rows: list[dict]) -> dict[str, set[str]]:
    ff: dict[str, set[str]] = {}
    for r in ffd_rows:
        file = (r.get("file") or r.get("WHFILE") or "").upper()
        field = (r.get("field") or r.get("WHFLDE") or "").upper()
        if file and field:
            ff.setdefault(file, set()).add(field)
    for r in db2_rows:
        table = (r.get("table") or r.get("TABLE_NAME") or "").upper()
        col = (r.get("column") or r.get("COLUMN_NAME") or "").upper()
        if table and col:
            ff.setdefault(table, set()).add(col)
    return ff


def resolve_path(program: str, src_root: Path | None) -> str:
    if src_root and src_root.exists():
        for p in src_root.rglob("*"):
            if p.is_file() and p.stem.upper() == program.upper():
                return p.as_posix()
    return f"as400://{program}"  # 合成 path(无源码时)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsppgmref", help="DSPPGMREF 导出 CSV")
    ap.add_argument("--dspffd", help="DSPFFD 导出 CSV")
    ap.add_argument("--db2cols", help="DB2 SYSCOLUMNS 导出 CSV(可选)")
    ap.add_argument("--src", help="AS400 源码根目录,用于把程序名解析成真实 path(可选)")
    ap.add_argument("--out", default="analysis/anchors.as400.json")
    args = ap.parse_args()

    pgmref = read_csv(args.dsppgmref)
    ffd = read_csv(args.dspffd)
    db2 = read_csv(args.db2cols)
    if not pgmref and not ffd and not db2:
        warn("没有任何输入 CSV;至少给一个 --dsppgmref / --dspffd / --db2cols")
        return 2

    file_fields = build_file_fields(ffd, db2)
    src_root = Path(args.src) if args.src else None

    # 按程序聚合引用
    prog: dict[str, dict] = {}
    for r in pgmref:
        program = (r.get("program") or r.get("WHPNAM") or "").upper()
        obj = (r.get("referenced_object") or r.get("WHFNAM") or "").upper()
        otype = (r.get("object_type") or r.get("WHOBJT") or "").upper()
        if not program:
            continue
        agg = prog.setdefault(program, {"tables": set(), "call_targets": set(), "screens": set(), "sql_tables": set()})
        if not obj:
            continue
        if otype in PGM_TYPES:
            agg["call_targets"].add(obj)
        elif otype in DSPF_HINT:
            agg["screens"].add(obj)
        else:  # 默认按文件/表处理(FILE/PF/LF 或未标类型)
            agg["tables"].add(obj)
            # 注意: DSPPGMREF 区分不了"经 SQL 访问"还是"RPG 原生 I/O",
            # 所以 sql_tables 留空(不臆断),仅 tables 记账。
            # 要 SQL 专属信息,用 SQL 包 / SYSPROGRAMSTAT 另行补充。

    # 若只有 DSPFFD 没有 DSPPGMREF,则把每个文件当成一个"单元"兜底
    if not prog and file_fields:
        for file in file_fields:
            prog[file] = {"tables": {file}, "call_targets": set(), "screens": set(), "sql_tables": set()}

    records = []
    for program, agg in sorted(prog.items()):
        fields: set[str] = set()
        for t in agg["tables"]:
            fields |= file_fields.get(t, set())
        records.append({
            "path": resolve_path(program, src_root),
            "side": "as400",
            "anchors": {
                "tables": sorted(agg["tables"]),
                "fields": sorted(fields),
                "programs": [program],
                "transactions": [],
                "screens": sorted(agg["screens"]),
                "call_targets": sorted(agg["call_targets"]),
                "sql_tables": sorted(agg["sql_tables"]),
            },
            # 来自 IBM i 平台交叉引用,权威。
            "anchor_confidence": 0.95,
            "extractor": "ibmi-outfile",
            "needs_authoritative_tool": False,
        })

    out = {
        "side": "as400",
        "source_root": args.src or "",
        "file_count": len(records),
        "extracted": len(records),
        "skipped_non_utf8": 0,
        "disclaimer": "来自 DSPPGMREF/DSPFFD/DB2 编目的权威交叉引用;比正则准。LLM 语义仍需 verify_semantics 对账。",
        "records": records,
    }
    write_json(Path(args.out), out)
    info(f"IBM i 锚点归一完成: {len(records)} 个程序单元 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
