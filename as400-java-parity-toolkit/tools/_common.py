"""共享工具函数(协调人离线脚本)。

设计约束:
- Python 3.10+,Windows 友好:一律用 pathlib,容忍路径含空格/中文。
- AS400 源码可能是 EBCDIC/codepage(非 UTF-8)。读取时显式指定编码,
  对疑似非 UTF-8 文件**告警跳过**而非崩溃。
- 所有 JSON 输出统一 UTF-8、ensure_ascii=False、缩进 2。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

# AS400 源码常见编码探测顺序。cp037/cp500 为常见 EBCDIC codepage。
# 注意:本工具不做真正的 EBCDIC 解码保证,仅 best-effort,失败则告警跳过。
_TEXT_ENCODINGS = ("utf-8", "utf-8-sig")


def warn(msg: str) -> None:
    """统一告警(stderr),不中断流程。"""
    print(f"[WARN] {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"[INFO] {msg}", file=sys.stderr)


def read_text_safe(path: Path) -> str | None:
    """显式编码读取文本。

    - 先按 UTF-8 系列尝试。
    - 失败(疑似 EBCDIC/二进制/codepage)则告警并返回 None,由调用方决定跳过。
    返回 None 表示"无法以 UTF-8 安全读取,需人工/专业工具处理"。
    """
    data = path.read_bytes()
    for enc in _TEXT_ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    warn(
        f"非 UTF-8 文件已跳过(疑似 EBCDIC/codepage,需专业抽取工具): {path}"
    )
    return None


def write_json(path: Path, obj) -> None:
    """统一 UTF-8 + ensure_ascii=False 写 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def iter_files(root: Path, suffixes: Iterable[str]) -> list[Path]:
    """递归收集指定后缀文件;后缀大小写不敏感。"""
    sset = {s.lower() for s in suffixes}
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in sset:
            out.append(p)
    return out


def rel(path: Path, base: Path) -> str:
    """相对路径,统一 posix 风格(跨平台稳定)。"""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
