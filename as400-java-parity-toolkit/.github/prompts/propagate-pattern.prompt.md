---
mode: agent
description: 把一个已定位的差异根因横扫两侧,产出分类风险点 N/M 清单(触发 propagate-pattern skill)
---

# /propagate-pattern

把**我当前定位到的一个差异根因**横扫两侧代码,找同类模式,产出"分类风险点 N 处 / 已验 M 处"。请使用 **propagate-pattern** skill。

按以下做:
1. 写清根因(可检索)+ 它属于哪个 `defect_class`。
2. 用根因特征(字段/运算/API)在两侧 semantics 与源码里搜同模式。
3. 把疑似同因规则补进相应 `analysis/diffs/<mapping_id>.json`(verdict 至少 uncertain,defect_class 一致,needs_runtime_test=true)。
4. 写传播报告 `analysis/diffs/<root_id>.propagation.md`(根因 + 命中清单 + N/M)。
5. 自检 `python tools/validate_outputs.py --path analysis/diffs --schema rule-diff`。
