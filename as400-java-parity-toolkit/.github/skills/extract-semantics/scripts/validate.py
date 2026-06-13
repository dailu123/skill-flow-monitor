"""skill 自检脚本:校验本步产物是否符合 semantics.schema.json。

agent 产出 JSON 后,自己跑一遍这个脚本,不过就改,过了再算完成。
复用 tools/validate_outputs.py 的同一套校验逻辑,避免两份标准漂移。

用法(在仓库根目录):
  python .github/skills/extract-semantics/scripts/validate.py analysis/semantics/AS4-0001-XXX.json
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))

from validate_outputs import validate_file  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python .../scripts/validate.py <产物.json>")
        return 2
    rc = 0
    for arg in sys.argv[1:]:
        errs = validate_file(Path(arg), "semantics")
        if errs:
            rc = 1
            print(f"[FAIL] {arg}")
            for e in errs[:20]:
                print(f"   - {e}")
        else:
            print(f"[ OK ] {arg}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
