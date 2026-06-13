---
mode: agent
description: 对当前领到的一个单元做语义抽取(显式入口,触发 extract-semantics skill)
---

# /extract-semantics

对**我当前领到的这一个单元**做语义抽取。请使用 **extract-semantics** skill 的方法与约束。

本步目标:把这个 AS400 或 Java 单元的行为抽取成结构化 JSON,锚点逐字保真,语义入固定 schema,低置信处标 `needs_human_review`。

按以下做:
1. 读我在 assignment 行里指向的源文件:#file
2. 严格按 `schemas/semantics.schema.json` 填写,unit_id / side 用 assignment 里的值。
3. 对照 `docs/DEFECT-CLASSES.md` 把涉及精度/排序/null/世纪/逻辑删除/事务边界的规则单独成条。
4. 写到 assignment 的 `artifact` 路径(`analysis/semantics/<unit_id>.json`),UTF-8。
5. 跑自检 `python .github/skills/extract-semantics/scripts/validate.py <artifact>`,不过就改到过。

只处理这一个单元,不要带入其它单元的上下文。
