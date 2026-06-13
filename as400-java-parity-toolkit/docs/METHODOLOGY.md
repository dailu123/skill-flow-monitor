# METHODOLOGY — 迁移对等性对比方法论

目标:**验证 Java 重写是否与 AS400 旧系统行为一致(迁移对等性)**,并枚举"还有多少行为差异"。
不是重写代码、不是翻译,而是**判定 + 取证 + 量化残差**。

## 十条原则

### 1. 锚点优先,语义为辅
先用确定性手段(专业工具 / best-effort 正则)抽锚点骨架:DB2 表/字段、程序/子程序、事务码、屏幕/显示文件 ID、CALL 目标、嵌入式 SQL 表。**共享数据模型(表/字段)是最强锚点**——两侧都绕着同一批表转,这比任何语义相似都可靠。LLM 语义只填补锚点之间的"行为"空白,**绝不拿语义当对齐主键**。

### 2. 语义抽进固定结构,不发散
两侧抽进同一 `semantics.schema.json`:inputs / outputs / 读写表 / 业务规则(离散断言)/ 分支 / 边界 / 错误路径。固定结构是为了**可对齐、可对比、可统计**。粒度要保住缺陷维度:精度、排序、null、世纪、逻辑删除、事务边界必须可见,不能糊成"处理了订单"。

### 3. 一桶对齐,孤心是一等公民
对齐产出三桶:`matched / as400_only / java_only`。**单侧桶最关键**——`as400_only` 是功能缺失(漏迁),`java_only` 是新增/口径变化,这两类是迁移风险的高发区,不得当残渣丢弃。映射允许 N:M(拆分/合并很常见)。

### 4. 语义匹配 ≠ 行为一致
这是全方法论的红线。语义看着一样,**只能产 `candidate_equivalent`(候选等价,待验)**,永远不能直接判 `equivalent`。真正的等价需要:规则级 diff 全 same + 运行时差异测试通过 + 人工背书。schema 层面 `pair_verdict` 根本没有 `equivalent` 这个值。

### 5. 对照已知缺陷类精细比对
带着 `docs/DEFECT-CLASSES.md` 的清单逐条过:EBCDIC 排序、packed/zoned 精度舍入、null/空白/空串、日期世纪窗口、逻辑删除、溢出截断、事务边界、figurative constant、动态查询条件范围。这些是 AS400→Java 的高频"看不见的坑"。

### 6. 与运行时差异证据交叉核对
若已有"双跑" diff,用 `import_runtime_diffs.py` 导入,在矩阵里高亮**"语义说相同、运行时说不同"**的对——这类是最值钱的发现(语义层骗过了你,运行时戳穿)。

### 7. 存疑项 → 运行时差异测试规格
对 `needs_runtime_test=true` 的规则,产出 difftest 规格:同输入喂两侧、比对输出与库表扫描、以 AS400 为 oracle。让结论被强 oracle 兜住,而不是停在"我觉得"。

### 8. 根因 → 同模式传播
每个 finding 写根因,按 `defect_class` 横扫两侧找同模式,产"分类风险点 N 处 / 已验 M 处"。一个舍入根因往往散在几十个程序里。

### 9. 置信度 + 人审
每条语义抽取/判断给 confidence。AS400/RPG 侧(定宽列、隐式精度、figurative constant)LLM 较弱,低置信处标 `needs_human_review`,交资深成员复核。

### 10. 风险分级 + 模型分档
海量初抽用便宜小模型;配对精细比对(compare-pair)用强模型。交易、审计、高频核心程序优先排期、优先上强模型与人审。

## 五步流水线

```
extract-semantics  →  align-mapping  →  compare-pair  →  generate-difftests  →  propagate-pattern
   (两侧各抽)          (锚点对齐分桶)     (规则级 diff)        (运行时 oracle 规格)     (根因横扫 N/M)
        |                   |                  |                      |                       |
analysis/semantics   analysis/mapping   analysis/diffs        analysis/tests         回填 diffs + 报告
        \__________________ 协调人离线: validate_outputs.py → aggregate_matrix.py → parity_matrix.json _____________/
```

每步一个 skill + 一个 `/` prompt 入口;每步产物有 schema;不过 schema 不算完成。
