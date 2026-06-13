"""extract_anchors.py — best-effort 确定性锚点抽取。

【重要 / 必读】
本脚本用**正则启发式**从源码抽取锚点(表/字段/程序/事务码/屏幕/CALL 目标/SQL 表)。
它**不是**一个 RPG/COBOL 解析器:
  - 对 RPG(尤其定宽 RPG III/RPGLE 定位列)抽取**不完整**,会漏会错。
  - 它**无法**改写/规范化字段名,只做粗粒度提取。
  - 凡正则把握不足之处,产出会标 confidence 低,需人工复核。

要拿到**权威锚点**,请用工业级抽取工具导出后喂给 build_units.py:
  - Fresche X-Analysis
  - ARCAD
  - IBM ADDI (Application Discovery and Delivery Intelligence)
本脚本仅用于"还没接专业工具时"的脚手架启动与冒烟演示。

用法:
  python tools/extract_anchors.py --src samples/as400 --side as400 --out analysis/anchors.as400.json
  python tools/extract_anchors.py --src samples/java  --side java  --out analysis/anchors.java.json
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import iter_files, read_text_safe, rel, write_json, info

# 各侧后缀。AS400 侧覆盖 RPG/CL/COBOL/DDS;Java 侧仅 .java。
SUFFIXES = {
    "as400": [".rpgle", ".rpg", ".sqlrpgle", ".clp", ".clle", ".cbl", ".cob", ".cblle", ".dds", ".pf", ".lf", ".dspf"],
    "java": [".java"],
}

# best-effort 正则。注释里标明"为什么不完整"。
PATTERNS_AS400 = {
    # 嵌入式 SQL 的表名;只抓 FROM/JOIN/INTO/UPDATE 后第一个标识符,漏掉子查询/多表别名。
    "sql_tables": re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Z][A-Z0-9_]*)", re.IGNORECASE),
    # F 规说明文件(RPG)。定宽列假设不严谨,RPGLE 自由式才较准。
    "tables": re.compile(r"^\s*F\s*([A-Z][A-Z0-9_]{0,9})\b", re.IGNORECASE | re.MULTILINE),
    # CALL/CALLP 目标。无法解析动态程序名变量。
    "call_targets": re.compile(r"\bCALL(?:P|B)?\s*\(?\s*'?([A-Z][A-Z0-9_]*)'?", re.IGNORECASE),
    # 事务码:无法从源码可靠推断,这里只抓形如 TXN/TRN 注释约定,基本会漏 -> 低 confidence。
    "transactions": re.compile(r"\b(?:TXN|TRN|TRANCODE)[\s:=]+([A-Z0-9]{2,8})", re.IGNORECASE),
    # 显示文件记录格式(DDS R 规)。
    "screens": re.compile(r"^\s*A\s+R\s+([A-Z][A-Z0-9_]*)", re.IGNORECASE | re.MULTILINE),
    # 程序名:用文件名兜底(见下方逻辑),这里抓 CL PGM。
    "programs": re.compile(r"\bPGM\b", re.IGNORECASE),
}

PATTERNS_JAVA = {
    # JPA/MyBatis 注解或 SQL 字符串里的表名,粗抓。
    "sql_tables": re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z][A-Za-z0-9_]*)", re.IGNORECASE),
    "tables": re.compile(r"@Table\s*\(\s*name\s*=\s*\"([A-Za-z0-9_]+)\"", re.IGNORECASE),
    # 跨服务调用粗抓:methodName( 形式无法判定是否为业务调用,故只抓显式 client.call。
    "call_targets": re.compile(r"\b([A-Za-z][A-Za-z0-9_]*Client)\b"),
    "transactions": re.compile(r"\b(?:TXN|TRANCODE)[\s:=\"]+([A-Za-z0-9]{2,8})"),
    "screens": re.compile(r"@(?:GetMapping|PostMapping|RequestMapping)\s*\(\s*\"([^\"]+)\""),
    "programs": re.compile(r"\bclass\s+([A-Za-z][A-Za-z0-9_]*)"),
}


def extract_one(text: str, side: str, file_stem: str) -> dict:
    pats = PATTERNS_AS400 if side == "as400" else PATTERNS_JAVA
    anchors: dict[str, list[str]] = {
        "tables": [], "fields": [], "programs": [], "transactions": [],
        "screens": [], "call_targets": [], "sql_tables": [],
    }
    for key, pat in pats.items():
        if key == "programs" and side == "as400":
            # CL PGM 无名,程序名用文件名兜底。
            anchors["programs"] = [file_stem.upper()]
            continue
        found = []
        for m in pat.finditer(text):
            if m.groups():
                found.append(m.group(1))
        anchors[key] = sorted(set(found))
    # 程序名兜底:文件名总是加入,保证最弱锚点存在。
    stem = file_stem if side == "java" else file_stem.upper()
    if stem not in anchors["programs"]:
        anchors["programs"].append(stem)
    # 字段:正则无法可靠抽取,留空并标记需专业工具。
    return anchors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="源码根目录")
    ap.add_argument("--side", required=True, choices=["as400", "java"])
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    args = ap.parse_args()

    root = Path(args.src)
    if not root.exists():
        info(f"源目录不存在: {root}")
        return 2

    files = iter_files(root, SUFFIXES[args.side])
    records = []
    skipped = 0
    for p in files:
        text = read_text_safe(p)
        if text is None:
            skipped += 1
            continue
        anchors = extract_one(text, args.side, p.stem)
        records.append({
            "path": rel(p, root),
            "side": args.side,
            "anchors": anchors,
            # 整体 confidence 低:best-effort 正则,字段缺失,需专业工具核对。
            "anchor_confidence": 0.4,
            "extractor": "regex-best-effort",
            "needs_authoritative_tool": True,
        })

    out = {
        "side": args.side,
        "source_root": rel(root, Path.cwd()) if root.is_absolute() is False else str(root),
        "file_count": len(files),
        "extracted": len(records),
        "skipped_non_utf8": skipped,
        "disclaimer": "正则启发式,锚点不完整;权威锚点请用 Fresche X-Analysis / ARCAD / IBM ADDI 导出。",
        "records": records,
    }
    write_json(Path(args.out), out)
    info(f"锚点抽取完成: {len(records)} 个单元, 跳过 {skipped} 个非 UTF-8 文件 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
