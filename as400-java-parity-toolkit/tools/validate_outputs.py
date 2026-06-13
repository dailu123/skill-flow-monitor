"""validate_outputs.py — 按 schema 校验所有 agent 产物。

未通过 schema 的 JSON **不计入 done**。本脚本既被协调人合并前批量跑,
也被各 skill 的 scripts/validate.py 复用同一套校验逻辑。

用法:
  python tools/validate_outputs.py                         # 校验 analysis/ 下全部产物
  python tools/validate_outputs.py --path analysis/semantics
  python tools/validate_outputs.py --file analysis/diffs/MAP-001.json --schema rule-diff
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover
    Draft7Validator = None

from _common import read_json, info, warn

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"

# 目录 -> schema 文件名(不含 .schema.json)
DIR_SCHEMA = {
    "semantics": "semantics",
    "mapping": "mapping",
    "diffs": "rule-diff",
    "tests": "difftest",
    "qa": "anchor-verify",
}


def load_schema(name: str) -> dict:
    return read_json(SCHEMA_DIR / f"{name}.schema.json")


def validate_file(path: Path, schema_name: str) -> list[str]:
    """返回错误信息列表;空列表表示通过。"""
    errors: list[str] = []
    try:
        obj = read_json(path)
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]

    if Draft7Validator is None:
        # 没装 jsonschema 时退化为最弱检查:必须是对象。
        warn("未安装 jsonschema,仅做最弱检查。请 pip install -r tools/requirements.txt")
        if not isinstance(obj, dict):
            errors.append("顶层应为对象")
        return errors

    schema = load_schema(schema_name)
    v = Draft7Validator(schema)
    for e in sorted(v.iter_errors(obj), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) or "(root)"
        errors.append(f"{loc}: {e.message}")
    return errors


def infer_schema(path: Path) -> str | None:
    for part in path.parts:
        if part in DIR_SCHEMA:
            return DIR_SCHEMA[part]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default="analysis", help="要校验的目录")
    ap.add_argument("--file", help="只校验单个文件")
    ap.add_argument("--schema", help="显式指定 schema 名(semantics/mapping/rule-diff/difftest/parity-matrix)")
    args = ap.parse_args()

    targets: list[tuple[Path, str]] = []
    if args.file:
        fp = Path(args.file)
        sname = args.schema or infer_schema(fp)
        if not sname:
            warn(f"无法推断 schema,请用 --schema 指定: {fp}")
            return 2
        targets.append((fp, sname))
    else:
        base = Path(args.path)
        for p in sorted(base.rglob("*.json")):
            sname = args.schema or infer_schema(p)
            if sname:
                targets.append((p, sname))

    total = len(targets)
    failed = 0
    for fp, sname in targets:
        errs = validate_file(fp, sname)
        if errs:
            failed += 1
            print(f"[FAIL] {fp}  (schema={sname})")
            for e in errs[:10]:
                print(f"        - {e}")
        else:
            print(f"[ OK ] {fp}  (schema={sname})")

    info(f"校验完成: {total - failed}/{total} 通过, {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
