---
name: generate-difftests
description: 当需要为有疑点的规则(needs_runtime_test=true)生成运行时差异测试规格时使用。同一输入喂 AS400 与 Java 两侧,比对输出字段与库表数据扫描,以 AS400 为 oracle,覆盖缺陷类边界用例(空集/溢出/世纪窗口/figurative constant)。产出写入 analysis/tests/<test_id>.json,符合 difftest.schema.json。迁移对等性分析第四步触发。
---

# generate-difftests — 运行时差异测试规格

为规则级 diff 里 `needs_runtime_test=true` 的规则生成可执行的**差异测试规格**(oracle)。本步只产出规格,不执行测试。

## 何时用
- 一个 mapping 的 compare-pair 完成,存在需要运行时定论的规则。
- 目标:让"语义说相同/不同"的结论能被运行时强 oracle 验证。

## 方法
1. **同输入双跑**:同一组输入喂两侧入口(`targets.as400` / `targets.java`),比对 `compare.outputs` 与 `compare.data_scan`(库表副作用,如逻辑删除标记)。
2. **以 AS400 为 oracle**(`expected_source: as400_is_oracle`),除非项目另有约定。
3. **边界用例针对缺陷类**:每个 needs_runtime_test 的规则,至少配一个戳中其 defect_class 的用例——空集合、数值溢出、世纪窗口临界(如 49/50)、*HIVAL 哨兵、EBCDIC 排序临界(数字与字母混排)、null vs 空白。
4. **容差显式**:packed/zoned 精度类容差应为 0,显式写进 `compare.tolerance` 以暴露舍入差异,而不是默默放过。
5. `covers_rules` 回指被覆盖的 rule-diff rule_id,便于结果回填矩阵。

## 步骤
1. 读对应 `analysis/diffs/<mapping_id>.json`,挑出 needs_runtime_test 的规则。
2. 设计输入用例集(覆盖正常 + 缺陷类边界)。
3. 定义比对项:输出字段 + data_scan 表/列/where。
4. 写到 `analysis/tests/<test_id>.json`,自检:
   ```
   python tools/validate_outputs.py --file analysis/tests/<test_id>.json --schema difftest
   ```

## 输出
- 路径:`analysis/tests/<test_id>.json`
- Schema:`schemas/difftest.schema.json`

## 参考
- `schemas/difftest.schema.json`
- `docs/DEFECT-CLASSES.md`(每类的边界用例提示)
