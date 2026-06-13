---
mode: agent
description: 对一个业务功能域把两侧语义单元按锚点对齐分桶(触发 align-mapping skill)
---

# /align-mapping

对**我当前领到的对齐工作项**(一个业务功能域 / 一组共享表),把两侧语义单元按共享锚点对齐。请使用 **align-mapping** skill。

按以下做:
1. 收集相关的两侧 `analysis/semantics/*.json`,读 `anchors`。
2. 以共享表/字段/事务码/CALL 目标为最强锚点聚类;语义相似只作补充,不当唯一证据。
3. 产出三桶之一(`matched / as400_only / java_only`),N:M 允许;单侧桶(缺失/新增)必须显式记录、标 `needs_human_review`。
4. 写到 `analysis/mapping/<mapping_id>.json`,符合 `schemas/mapping.schema.json`。
5. 自检 `python tools/validate_outputs.py --file analysis/mapping/<mapping_id>.json --schema mapping`。
