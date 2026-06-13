---
mode: agent
description: 为有疑点的规则生成运行时差异测试规格(触发 generate-difftests skill)
---

# /generate-difftests

为**我当前领到的 mapping** 里 `needs_runtime_test=true` 的规则生成运行时差异测试规格。请使用 **generate-difftests** skill。本步只产出规格,不执行。

按以下做:
1. 读 `analysis/diffs/<mapping_id>.json`,挑出 needs_runtime_test 的规则。
2. 设计同输入双跑用例,覆盖缺陷类边界(空集/溢出/世纪窗口临界/figurative constant/EBCDIC 排序临界/null vs 空白)。
3. 定义比对项:输出字段 + 库表 data_scan;精度类容差显式置 0。
4. `expected_source` 默认 `as400_is_oracle`;`covers_rules` 回指 rule_id。
5. 写到 `analysis/tests/<test_id>.json`,符合 `schemas/difftest.schema.json`。
6. 自检 `python tools/validate_outputs.py --file analysis/tests/<test_id>.json --schema difftest`。
