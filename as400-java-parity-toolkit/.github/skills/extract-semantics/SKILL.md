---
name: extract-semantics
description: 当需要把单个 AS400(RPG/CL/COBOL/DDS)或 Java 单元的行为抽取为结构化语义 JSON 时使用。锚点保真、语义入固定 schema、低置信标记人工复核。产出写入 analysis/semantics/<unit_id>.json,符合 semantics.schema.json。在 migration parity(迁移对等性)分析的第一步、对单个分析单元时触发。
---

# extract-semantics — 单元语义抽取

把**一个**分析单元的行为抽取成结构化 JSON。这是流水线第一步,**只处理 assignment 里当前这一个 unit**,不要跨单元串联上下文。

## 何时用
- 你从 `analysis/assignments/<你的名字>.csv` 领到一个 `status != done` 的单元,prompt 列是 `/extract-semantics`。
- 一个新 Chat 只做一个单元;做完即关,不要把上一个单元的内容带进来。

## 方法(必须遵守,完整方法论见 `docs/METHODOLOGY.md`)
1. **锚点保真**:`anchors` 里的表/字段/程序/事务码/屏幕/CALL 目标/SQL 表,直接来自源码或专业工具导出,**逐字照抄,不改写、不归一**。这是对齐的最强依据,语义只是补充。
2. **语义入固定结构,不发散**:严格按 `schemas/semantics.schema.json` 填 `inputs/outputs/reads_writes/rules/branches/boundaries/error_paths`。
3. **粒度保住缺陷维度**:`rules` 拆成可证伪的离散断言。凡涉及数值精度、排序、null/空白、日期世纪、逻辑删除、事务边界处,必须单独成条,别糊成一句。对照 `docs/DEFECT-CLASSES.md` 自查。
4. **置信度 + 人工复核**:每条 rule 和整体都给 `confidence`(0~1)。AS400/RPG 侧 LLM 较弱,凡定宽列、隐式精度、figurative constant 处置信度调低,并把 `needs_human_review` 置 `true`。
5. **不臆造**:读不到/看不懂的地方,写进 `boundaries` 或 `notes` 说明"未确定",降低 confidence,**不要编**。

## 步骤
1. 打开 assignment 指向的源文件(`#file` 引用),只读这一个单元。
2. 若该侧已有 `analysis/anchors.<side>.json` 中对应记录,把锚点抄进 `anchors`;否则从源码 best-effort 提取并标注不确定。
3. 按 schema 逐字段填写,unit_id 用 assignment 里的值,side 与之一致。
4. 写到 assignment 的 `artifact` 路径(`analysis/semantics/<unit_id>.json`),UTF-8。
5. **自检**:运行
   ```
   python .github/skills/extract-semantics/scripts/validate.py <artifact路径>
   ```
   不通过就改,通过了这个单元才算完成。

## 输出
- 路径:`analysis/semantics/<unit_id>.json`
- Schema:`schemas/semantics.schema.json`(self-contained,字段含义见 schema 内 description)

## 参考(渐进加载,需要时再读)
- `schemas/semantics.schema.json`
- `docs/DEFECT-CLASSES.md`
- `docs/METHODOLOGY.md`
