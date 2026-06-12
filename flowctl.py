#!/usr/bin/env python3
"""flowctl.py — skill 埋点命令行工具（纯标准库，无依赖）。

skill 在运行过程中调用本脚本更新状态 JSON，浏览器 UI 每秒轮询自动刷新。

用法示例:
  # ── Skill 流水线 ──────────────────────────────────────────
  python flowctl.py skill convert-sql running --progress 30 --detail "正在转换 STG_ORDERS_AGG" --name "RPG → SQL 转换"
  python flowctl.py skill convert-sql done
  python flowctl.py skill convert-sql error --detail "解析 ORDR042 失败"
  python flowctl.py link scan lineage              # 添加 skill 之间的连线

  # ── ETL 血缘树 ────────────────────────────────────────────
  python flowctl.py set-target RPT_SALES_SUMMARY
  python flowctl.py add-node ORDERS_PF --type rpg --feeds STG_ORDERS_AGG   # 溯源到一个上游就加一个节点
  python flowctl.py node ORDERS_PF running --progress 40 --detail "解析 DDS"
  python flowctl.py node ORDERS_PF done

  # ── 其他 ─────────────────────────────────────────────────
  python flowctl.py reset all                      # 清空两个图，开始新一轮迁移
  python flowctl.py title "ORDR 系列迁移"           # 设置页面标题

状态取值: pending | running | done | error | skipped
节点类型: table | view | file | rpg | cl | cobol | sql | python
环境变量 FLOW_STATUS_DIR 可覆盖状态文件目录（默认 <本脚本目录>/public/status）。
"""

import argparse
import datetime
import json
import os
import sys
import tempfile

STATUS_DIR = os.environ.get("FLOW_STATUS_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "public", "status"
)
PIPELINE_FILE = os.path.join(STATUS_DIR, "pipeline.json")
LINEAGE_FILE = os.path.join(STATUS_DIR, "lineage.json")

STATUSES = ("pending", "running", "done", "error", "skipped")


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save(path, data):
    data["updatedAt"] = now()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # 原子写入，避免 UI 读到半截 JSON


def find_or_create(items, item_id, defaults):
    for it in items:
        if it["id"] == item_id:
            return it
    it = {"id": item_id, **defaults}
    items.append(it)
    return it


def apply_status(item, status, args):
    item["status"] = status
    if args.detail is not None:
        item["detail"] = args.detail
    if args.progress is not None:
        item["progress"] = max(0, min(100, args.progress))
    if status == "running" and "startedAt" not in item:
        item["startedAt"] = now()
    if status == "done":
        item["progress"] = 100
        item["endedAt"] = now()
    if status == "error":
        item["endedAt"] = now()


def add_edge(edges, src, dst):
    if not any(e["from"] == src and e["to"] == dst for e in edges):
        edges.append({"from": src, "to": dst})


def cmd_skill(args):
    data = load(PIPELINE_FILE, {"title": "迁移流水线", "skills": [], "edges": []})
    skill = find_or_create(
        data["skills"], args.id, {"name": args.id, "status": "pending", "progress": 0, "detail": ""}
    )
    if args.name:
        skill["name"] = args.name
    apply_status(skill, args.status, args)
    save(PIPELINE_FILE, data)
    print(f"[flowctl] skill {args.id} -> {args.status}")


def cmd_link(args):
    data = load(PIPELINE_FILE, {"title": "迁移流水线", "skills": [], "edges": []})
    add_edge(data["edges"], args.src, args.dst)
    save(PIPELINE_FILE, data)
    print(f"[flowctl] link {args.src} -> {args.dst}")


def cmd_node(args):
    data = load(LINEAGE_FILE, {"target": "", "nodes": [], "edges": []})
    node = find_or_create(
        data["nodes"], args.id, {"label": args.id, "type": "table", "status": "pending", "progress": 0, "detail": ""}
    )
    if args.label:
        node["label"] = args.label
    if args.type:
        node["type"] = args.type
    apply_status(node, args.status, args)
    save(LINEAGE_FILE, data)
    print(f"[flowctl] node {args.id} -> {args.status}")


def cmd_add_node(args):
    data = load(LINEAGE_FILE, {"target": "", "nodes": [], "edges": []})
    node = find_or_create(
        data["nodes"], args.id, {"label": args.id, "type": "table", "status": "pending", "progress": 0, "detail": ""}
    )
    if args.label:
        node["label"] = args.label
    if args.type:
        node["type"] = args.type
    if args.status:
        node["status"] = args.status
    if args.detail is not None:
        node["detail"] = args.detail
    for target in filter(None, (args.feeds or "").split(",")):
        find_or_create(data["nodes"], target.strip(), {"label": target.strip(), "type": "table", "status": "pending", "progress": 0, "detail": ""})
        add_edge(data["edges"], args.id, target.strip())
    save(LINEAGE_FILE, data)
    print(f"[flowctl] add-node {args.id}" + (f" feeds {args.feeds}" if args.feeds else ""))


def cmd_set_target(args):
    data = load(LINEAGE_FILE, {"target": "", "nodes": [], "edges": []})
    data["target"] = args.id
    find_or_create(data["nodes"], args.id, {"label": args.id, "type": "table", "status": "pending", "progress": 0, "detail": ""})
    save(LINEAGE_FILE, data)
    print(f"[flowctl] target = {args.id}")


def cmd_title(args):
    data = load(PIPELINE_FILE, {"title": "迁移流水线", "skills": [], "edges": []})
    data["title"] = args.text
    save(PIPELINE_FILE, data)
    print(f"[flowctl] title = {args.text}")


def cmd_reset(args):
    if args.which in ("pipeline", "all"):
        save(PIPELINE_FILE, {"title": "迁移流水线", "skills": [], "edges": []})
    if args.which in ("lineage", "all"):
        save(LINEAGE_FILE, {"target": "", "nodes": [], "edges": []})
    print(f"[flowctl] reset {args.which}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("skill", help="更新一个 skill 的状态")
    p.add_argument("id")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--progress", type=int)
    p.add_argument("--detail")
    p.add_argument("--name")
    p.set_defaults(func=cmd_skill)

    p = sub.add_parser("link", help="添加 skill 之间的连线")
    p.add_argument("src")
    p.add_argument("dst")
    p.set_defaults(func=cmd_link)

    p = sub.add_parser("node", help="更新一个血缘节点的状态")
    p.add_argument("id")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--progress", type=int)
    p.add_argument("--detail")
    p.add_argument("--label")
    p.add_argument("--type")
    p.set_defaults(func=cmd_node)

    p = sub.add_parser("add-node", help="添加血缘节点（含连向下游的边）")
    p.add_argument("id")
    p.add_argument("--label")
    p.add_argument("--type")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--detail")
    p.add_argument("--feeds", help="该节点的下游节点 id，逗号分隔")
    p.set_defaults(func=cmd_add_node)

    p = sub.add_parser("set-target", help="设置血缘树的目标表")
    p.add_argument("id")
    p.set_defaults(func=cmd_set_target)

    p = sub.add_parser("title", help="设置页面标题")
    p.add_argument("text")
    p.set_defaults(func=cmd_title)

    p = sub.add_parser("reset", help="清空状态文件")
    p.add_argument("which", choices=("pipeline", "lineage", "all"))
    p.set_defaults(func=cmd_reset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
