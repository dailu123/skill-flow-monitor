#!/usr/bin/env bash
# 模拟一轮 AS400 迁移，让监控页面动起来。每步之间停顿，方便肉眼观察动效。
set -e
cd "$(dirname "$0")"
F="python3 flowctl.py"
S=2  # 每步间隔秒数

step() { sleep "$S"; }

# ── 重置 ───────────────────────────────
$F reset all
$F title "ORDR 销售汇总迁移（模拟）"

# ── 登记 skill 流水线的连线骨架 ─────────
$F skill scan        pending --name "扫描 AS400 源码"
$F skill lineage     pending --name "血缘溯源分析"
$F skill convert-sql pending --name "RPG → SQL 转换"
$F skill convert-py  pending --name "CL → Python 转换"
$F skill validate    pending --name "结果数据校验"
$F skill report      pending --name "生成迁移报告"
$F link scan lineage
$F link lineage convert-sql
$F link lineage convert-py
$F link convert-sql validate
$F link convert-py validate
$F link validate report
step

# ── 1. 扫描源码 ────────────────────────
$F skill scan running --progress 20 --detail "读取 QSYS 库成员"; step
$F skill scan running --progress 70 --detail "解析 42 个 RPG / DDS"; step
$F skill scan done --detail "解析完成：42 个成员"; step

# ── 2. 血缘分析 + 同步在血缘图里长出节点 ─
$F skill lineage running --progress 15 --detail "确定目标表"
$F set-target RPT_SALES_SUMMARY; step
$F skill lineage running --progress 40 --detail "溯源第一层上游"
$F add-node STG_ORDERS_AGG  --type sql    --feeds RPT_SALES_SUMMARY
$F add-node STG_CUSTOMER_DIM --type python --feeds RPT_SALES_SUMMARY; step
$F skill lineage running --progress 75 --detail "溯源到物理文件层"
$F add-node ORDERS_PF   --type rpg --feeds STG_ORDERS_AGG
$F add-node ORDLINES_PF --type rpg --feeds STG_ORDERS_AGG
$F add-node CUSTMAST_PF --type rpg --feeds STG_CUSTOMER_DIM; step
$F skill lineage done --detail "构建 6 节点依赖树"; step

# ── 3. 按编号顺序（最远源头优先）转换节点 ─
$F skill convert-sql running --progress 10 --detail "从最源头开始"; step
for n in ORDERS_PF ORDLINES_PF CUSTMAST_PF; do
  $F node $n running --progress 50 --detail "解析 DDS 字段定义"; step
  $F node $n done --detail "字段映射完成"; step
done

$F skill convert-sql running --progress 55 --detail "翻译汇总逻辑"
$F node STG_ORDERS_AGG running --progress 45 --detail "RPG 累加 → SQL GROUP BY"; step
$F node STG_ORDERS_AGG done --detail "已生成 stg_orders_agg.sql"
$F skill convert-sql done --detail "SQL 全部生成"; step

$F skill convert-py running --progress 50 --detail "生成 pandas 清洗脚本"
$F node STG_CUSTOMER_DIM running --progress 60 --detail "CL 清洗 → pandas"; step
$F node STG_CUSTOMER_DIM done --detail "已生成 stg_customer_dim.py"
$F skill convert-py done --detail "Python 脚本生成完成"; step

$F node RPT_SALES_SUMMARY running --progress 50 --detail "拼装最终汇总查询"; step
$F node RPT_SALES_SUMMARY done --detail "已生成 rpt_sales_summary.sql"; step

# ── 4. 校验 + 报告（演示一次失败再恢复）──
$F skill validate running --progress 40 --detail "比对行数与金额"; step
$F skill validate error --detail "STG_ORDERS_AGG 金额差 0.02%"; step
$F skill validate running --progress 80 --detail "修正舍入后重校验"; step
$F skill validate done --detail "校验通过"; step

$F skill report running --progress 60 --detail "汇总迁移结果"; step
$F skill report done --detail "报告已输出 migration_report.md"

echo "[simulate] 完成"
