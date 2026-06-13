# Copilot 项目指令 — AS400 → Java 迁移对等性对比

本仓库是一套**人机协同对比脚手架**:10 人在 VS Code 的 GitHub Copilot **Agent 模式**里,逐单元判定 Java 重写是否与 AS400 旧系统**行为一致**,并枚举"还有多少行为差异"。**没有 Copilot CLI**——LLM 步骤全靠人在 agent 里手动驱动,确定性活由协调人离线跑 Python。

旧系统:AS400 / IBM i(RPG III/IV、RPGLE、CL、COBOL、DDS、显示文件、嵌入式 SQL)。新系统:Java 重写。

## 方法论(每一步都遵守)
1. **锚点优先,语义为辅。** 先用确定性 Python/专业工具抽锚点骨架(DB2 表/字段、程序/子程序、事务码、屏幕/显示文件 ID、CALL 目标、SQL 表),**以共享数据模型(表/字段)为最强锚点**。LLM 语义只补充,**绝不拿语义匹配主键**。
2. **语义抽进固定结构,不发散。** 两侧抽进同一 schema:inputs / outputs / 读写表 / 业务规则(离散断言)/ 分支条件 / 边界处理 / 错误路径。粒度必须保住缺陷维度。
3. **一桶对齐,孤心是一等公民。** 产出 `matched / as400_only / java_only`;单侧两类(功能缺失/新增)最高优先,不得当残渣。映射允许 N:M。
4. **语义匹配 ≠ 行为一致。** 语义相同只能产 `candidate_equivalent`(候选等价,待验证),**永远不能直接判 `equivalent`**。定论只来自规则级 diff + 运行时差异测试。
5. **对照已知缺陷类精细比对**(见 `docs/DEFECT-CLASSES.md`):EBCDIC vs Java 排序、packed/zoned 精度与舍入、null vs 空白 vs 空串、日期世纪窗口、逻辑删除语义、数值溢出/字段截断、事务/提交边界、figurative constant、动态条件查询(OPNQRYF/嵌入式 SQL → Java 动态 SQL)的空条件与范围边界。
6. **与运行时差异证据交叉核对。** 可导入已有运行时 diff;高亮"语义说相同、运行时说不同"的对。
7. **存疑项 → 生成运行时差异测试规格**(同输入喂两侧、比对输出与数据扫描),让结论被强 oracle 兜住。
8. **根因 → 同模式传播。** 每个 finding 写根因,横扫两侧同类模式,产"分类风险点 N 处 / 已验 M 处"。
9. **置信度 + 人审。** 每条 LLM 语义抽取给 confidence;AS400 侧低置信标 `needs_human_review`(RPG 上 LLM 较弱)。
10. **风险分级 + 模型分档。** 海量抽取用便宜小模型,配对精细比对用强模型;交易/审计/高频核心程序优先。

## 协同纪律(10 人 · 无 CLI)
- **每个单元开一个全新 Chat**(点新建会话),做完即关,**绝不跨单元携带上下文**——这是"独立运行"的唯一实现方式。
- **按域逐渐领题**:从 `analysis/assignments/<你的名字>.csv` 取下一个 `status != done` 的单元;做完把产物写到约定路径。
- **进度按"产物文件是否存在 + schema 是否通过"自动判定**(`tools/progress.py`),尽量不手改 status,避免 10 人状态打架。
- **产物用 git 合并**:每人一个分支(或子目录),协调人统一合并 + 跑汇总;JSON 产物必须 schema 合法才算完成。

## 产物与 schema(合同)
| 步骤 | skill / prompt | 产物 | schema |
| --- | --- | --- | --- |
| 语义抽取 | extract-semantics | analysis/semantics/<unit_id>.json | semantics |
| 对齐分桶 | align-mapping | analysis/mapping/<mapping_id>.json | mapping |
| 规则级对比 | compare-pair | analysis/diffs/<mapping_id>.json | rule-diff |
| 差异测试规格 | generate-difftests | analysis/tests/<test_id>.json | difftest |
| 根因传播 | propagate-pattern | analysis/diffs/<root_id>.propagation.md (+ 回填 diffs) | rule-diff |

产物写完务必自检:`python tools/validate_outputs.py ...`,不过不算完成。

## 给 agent 的硬规矩
- 锚点逐字照抄,不改写。
- 只写 `analysis/`,不碰源码/schema/tools。
- 拿不准写 `uncertain` + `needs_runtime_test=true`,**不要赌成 same / equivalent**。
- 一个会话只做一个单元/工作项。
