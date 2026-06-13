---
name: propagate-pattern
description: 当一个差异已定位根因、需要把同类模式扫遍两侧代码并产出"分类风险点 N 处/已验 M 处"清单时使用。每个 finding 写一个根因,按缺陷类把同模式横扫,标记疑似同因的其它单元。产出更新 analysis/diffs 与一个 propagation 报告。迁移对等性分析第五步(根因传播)触发。
---

# propagate-pattern — 根因与同模式传播

把一个已定位的差异**根因**,横扫两侧找同类模式,产出"分类风险点 N / 已验 M"清单。一个差异往往不是孤例。

## 何时用
- compare-pair / difftest 发现一个确凿差异,且能归纳出根因(如"Java 用了 ROUND_HALF_UP 而 AS400 是 half-adjust 截断")。
- 想知道这个根因还潜伏在哪些单元。

## 方法
1. **写根因**:一句可检索的根因描述 + 它属于哪个 `defect_class`。
2. **按模式横扫**:用根因的锚点/特征(涉及的字段、运算、API)在两侧 semantics 与源码里搜同类位置。
3. **产出风险点清单**:命中即记为"分类风险点"(N),其中已有 difftest 结论的记为"已验"(M)。给每个命中点标 `confidence` 与是否 `needs_runtime_test`。
4. **回填**:把新发现的疑似同因规则补进相应 `analysis/diffs/<mapping_id>.json`(verdict 至少 uncertain,defect_class 一致,needs_runtime_test=true),让 aggregate_matrix.py 能统计到 N/M。

## 步骤
1. 选定一个根因,确定 defect_class。
2. 横扫两侧,列出疑似同模式单元/规则。
3. 更新相关 diffs(补规则)并写一份传播报告(放 `analysis/diffs/` 同目录的 `<root_id>.propagation.md`,人读)。
4. 自检改动过的 diffs:
   ```
   python tools/validate_outputs.py --path analysis/diffs --schema rule-diff
   ```

## 输出
- 更新:`analysis/diffs/<mapping_id>.json`(补充同因规则)
- 报告:`analysis/diffs/<root_id>.propagation.md`(根因 + 命中清单 + N/M)

## 参考
- `docs/DEFECT-CLASSES.md`
- `docs/METHODOLOGY.md`(第 8 条:根因 → 同模式传播)
