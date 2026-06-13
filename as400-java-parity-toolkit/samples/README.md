# 最小样例 — 端到端演示

两对 RPG/Java 配对 + 一份 units/assignments,演示一个成员在 Copilot agent 里跑
`/extract-semantics → /compare-pair`,以及协调人跑 `aggregate_matrix.py` 的输出样子。
**这些只是脚手架演示,不是真实生产码。**

## 配对
| mapping | 业务功能 | AS400 | Java | 故意埋的缺陷类 |
| --- | --- | --- | --- | --- |
| MAP-001 | 订单折扣计算 | `as400/CALCDISC.sqlrpgle` | `java/DiscountService.java` | logical-delete(漏过滤 DEL_STS)、packed-zoned-precision(HALF_EVEN vs half-adjust) |
| MAP-002 | 客户范围检索 | `as400/CUSTSRCH.sqlrpgle` | `java/CustomerSearch.java` | ebcdic-sort(排序序)、figurative-constant(*LOVAL/*HIVAL vs 空串) |

`samples/units.csv` 与 `samples/assignments/alice.csv` 是建题/分配的样子。

## 成员视角(在 Copilot Agent 模式)
1. 打开 `samples/assignments/alice.csv`,挑第一个产物不存在的单元(如 AS4-0001-CALCDISC)。
2. 新建 Chat(选 `parity-analyzer` agent),打开 `samples/as400/CALCDISC.sqlrpgle`,输入 `/extract-semantics`。
   → 产出 `analysis/semantics/AS4-0001-CALCDISC.json`(本仓库已附上示例产物)。
3. 两侧语义都抽完后,对齐成 `analysis/mapping/MAP-001.json`(`/align-mapping`)。
4. 新建 Chat,输入 `/compare-pair`,对 MAP-001 做规则级对比 → `analysis/diffs/MAP-001.json`。
   注意结果:两条规则 verdict=different,pair_verdict=different,均 needs_runtime_test=true。
5. MAP-002 演示红线:语义层看不出差异 → pair_verdict=**candidate_equivalent**(绝不 equivalent),两条 needs_runtime_test=true。

> 本目录已附上步骤 2~5 的**示例产物**(在 `analysis/` 下),让你不跑 agent 也能直接看汇总效果。

## 协调人视角(离线 Python)
```bat
:: 导入运行时 diff(样例 dump 在 samples/runtime_dumps/)
python tools\import_runtime_diffs.py --in samples\runtime_dumps --out analysis\runtime_diffs.json

:: 校验全部产物
python tools\validate_outputs.py --path analysis

:: 汇总对等性矩阵
python tools\aggregate_matrix.py --analysis analysis --out analysis\parity_matrix.json
```

预期 `aggregate_matrix.py` stdout 会显示:
- 单侧桶:matched=2,as400_only=0,java_only=0
- 分类风险点(N 命中 / M 已验):logical-delete、packed-zoned-precision、ebcdic-sort、figurative-constant 各 1
- ⚠ **语义说相同 但 运行时说不同**:MAP-002(客户编号范围检索)—— EBCDIC 排序序在运行时被戳穿。

这正是方法论第 4、6 条的落地:**语义匹配 ≠ 行为一致**,运行时证据兜底。
