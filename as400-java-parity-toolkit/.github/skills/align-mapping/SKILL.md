---
name: align-mapping
description: 当需要把 AS400 侧与 Java 侧的语义单元按共享锚点对齐、产出 matched/as400_only/java_only 三桶时使用。以表/字段等共享数据模型为最强锚点,语义相似只作补充。产出写入 analysis/mapping/<mapping_id>.json,符合 mapping.schema.json。在迁移对等性分析第二步(对齐阶段)触发。
---

# align-mapping — 单元对齐分桶

把两侧 `analysis/semantics/*.json` 按**共享锚点**对齐,产出对齐记录,落到三桶之一:`matched / as400_only / java_only`。

## 何时用
- 语义抽取已完成一批,进入对齐阶段。
- 你领到一个"对齐工作项"(一个业务功能域 / 一组共享表)。

## 方法(必须遵守)
1. **以锚点对齐,不靠语义猜主键**:对齐证据(`anchor_evidence`)必须是共享的表/字段/事务码/CALL 目标。`以共享数据模型(表/字段)为最强锚点`。语义相似**不能**作为唯一证据。
2. **三桶齐全,孤心优先**:
   - `matched`:两侧都有,N:M 允许(一个 AS400 程序对多个 Java 类,反之亦然)。
   - `as400_only`:Java 缺失 → 功能缺失,**高优先级**。
   - `java_only`:Java 新增 → 可能多做/口径变了,**高优先级**。
   单侧桶不得当残渣丢弃,要显式记录并标 `needs_human_review`。
3. **置信度 + 复核**:对齐 `confidence`;弱锚点(仅靠程序名/语义)对齐置信度调低、置 `needs_human_review`。

## 步骤
1. 收集本工作项相关的两侧 semantics JSON,读它们的 `anchors`。
2. 按共享锚点聚类:同表/同字段/同事务码的单元归为候选对。
3. 为每个聚类产出一条 mapping:选 bucket、列 as400_units / java_units、填 anchor_evidence、business_function。
4. 落单侧桶:有 AS400 无 Java → as400_only;反之 java_only。
5. 写到 `analysis/mapping/<mapping_id>.json`,自检:
   ```
   python tools/validate_outputs.py --file analysis/mapping/<mapping_id>.json --schema mapping
   ```

## 输出
- 路径:`analysis/mapping/<mapping_id>.json`
- Schema:`schemas/mapping.schema.json`

## 参考
- `schemas/mapping.schema.json`
- `docs/METHODOLOGY.md`(第 3 条:一桶对齐,孤心是一等公民)
