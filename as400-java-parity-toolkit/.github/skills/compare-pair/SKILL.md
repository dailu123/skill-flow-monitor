---
name: compare-pair
description: 当需要对一个已对齐的 AS400↔Java 对做规则级精细对比时使用。逐条规则对照已知缺陷类(EBCDIC 排序、packed/zoned 精度、null/空白、世纪窗口、逻辑删除、溢出截断、事务边界、figurative constant、动态查询条件等),语义一致只能产出 candidate_equivalent 绝不直接判 equivalent。产出写入 analysis/diffs/<mapping_id>.json,符合 rule-diff.schema.json。迁移对等性分析第三步(精细对比)触发。
---

# compare-pair — 规则级精细对比

对**一个** `matched` 对做逐规则对比,产出 rule-diff。这是判定差异的核心步骤。

## 何时用
- 一个 mapping 已对齐(bucket=matched),需要判定两侧行为是否一致。
- 你领到一个 compare 工作项,对应一个 mapping_id。

## 铁律(违反即作废)
- **语义匹配 ⇒ 最多 `candidate_equivalent`,永远不能直接判 `equivalent`。** `pair_verdict` 取值只有 `candidate_equivalent | different | uncertain`,schema 里**没有** equivalent。真正的"等价"只能由规则全 same + 运行时差异测试通过后,在矩阵层由人工背书。
- **每条规则必须对照下面的 DEFECT-CLASSES 逐项过筛。** 命中就填 `defect_class`,并把 `needs_runtime_test` 置 true。
- **拿不准就 `uncertain` + `needs_runtime_test=true`**,不要赌成 same。

## DEFECT-CLASSES 检查清单(逐条过;完整定义见 `docs/DEFECT-CLASSES.md`)
对每条规则,问这些问题,命中则记 `defect_class`:
1. **ebcdic-sort** — 涉及排序/比较/范围?AS400 是 EBCDIC 排序序(数字>字母、大小写顺序不同),Java 默认 Unicode/ASCII 序。ORDER BY、`>`/`<`、SETLL/READE 范围都查。
2. **packed-zoned-precision** — 涉及 packed/zoned decimal 运算?定点精度、半上舍入 vs Java `double`/`BigDecimal` 舍入模式、scale 截断。
3. **null-blank-empty** — AS400 的空白(*BLANKS)、零(*ZEROS)、SQL NULL 在 Java 里被映射成 null / "" / "   " 哪一种?三者语义不同。
4. **date-century-window** — 两位年份的世纪窗口(如 40 → 1940 还是 2040)、日期合法性、6 位/8 位日期格式。
5. **logical-delete** — 逻辑删除标记(如 DEL_STATUS/DLT_FLG)语义:AS400 读时是否过滤?Java 是否同样过滤?物理删 vs 逻辑删。
6. **numeric-overflow-truncation** — 字段位宽溢出行为(AS400 截高位 vs Java 异常/进位)、中间结果字段截断。
7. **transaction-commit-boundary** — COMMIT/ROLLBACK 边界、提交粒度、隔离级别;一个 AS400 工作单元是否对应一个 Java 事务。
8. **figurative-constant** — *HIVAL/*LOVAL/*BLANKS/*ZEROS/*ALL 在比较与赋值中的语义,Java 是否等价复现(尤其 *HIVAL 用作哨兵 key)。
9. **dynamic-query-condition-range** — OPNQRYF / 嵌入式 SQL 动态条件 → Java 动态 SQL:空条件(无过滤)、范围边界(含/不含端点)、可选过滤拼接是否一致。
10. 其它结构性差异填 `other`,完全无关填 `none`。

## 步骤
1. 读这个 mapping 的两侧 semantics(`as400_units` / `java_units`)。
2. 对 AS400 侧每条 rule,找 Java 侧对应断言;逐条按上面清单过筛。
3. 每条产出:`rule_id, as400_assertion, java_assertion, verdict(same|different|uncertain), defect_class, confidence, evidence, needs_runtime_test`。
4. AS400 侧缺、Java 多 → 也成条(java_assertion 或 as400_assertion 留空,verdict=different)。
5. 给 `pair_verdict`:有任一 different → different;全 same 且无未决 → candidate_equivalent;否则 uncertain。
6. 写到 `analysis/diffs/<mapping_id>.json`,自检:
   ```
   python tools/validate_outputs.py --file analysis/diffs/<mapping_id>.json --schema rule-diff
   ```

## 输出
- 路径:`analysis/diffs/<mapping_id>.json`
- Schema:`schemas/rule-diff.schema.json`

## 参考
- `docs/DEFECT-CLASSES.md`(逐类定义、AS400 行为、Java 易错点、判别问句)
- `schemas/rule-diff.schema.json`
