#!/usr/bin/env bash
# 复杂场景：销售利润数据集市迁移。
# 血缘树 4 层 22 个对象，含菱形依赖；流水线 11 个 skill 带并行分支。
set -e
cd "$(dirname "$0")"
F="python3 flowctl.py"
S=${1:-1.6}   # 间隔秒数，可传参覆盖：bash simulate-complex.sh 3
step() { sleep "$S"; }

$F reset all
$F title "销售利润数据集市迁移 · DM_SALES_PROFIT_MART（复杂模拟）"

# ════════════════════════════════════════════════════════════
# 一、流水线骨架（11 个 skill，带并行分支）
# ════════════════════════════════════════════════════════════
$F skill scan         pending --name "扫描 AS400 库"
$F skill parse-dds    pending --name "解析 DDS / 字段"
$F skill lineage      pending --name "血缘溯源分析"
$F skill conv-source  pending --name "源表(PF/LF) → DDL"
$F skill conv-stg     pending --name "清洗层 → SQL"
$F skill conv-dim     pending --name "维度表 → SQL"
$F skill conv-fact    pending --name "事实表 → SQL"
$F skill conv-cl      pending --name "CL 作业 → Python 调度"
$F skill conv-mart    pending --name "集市层 → SQL"
$F skill validate     pending --name "全链路数据校验"
$F skill report       pending --name "生成迁移报告"

$F link scan parse-dds
$F link parse-dds lineage
$F link lineage conv-source
$F link conv-source conv-stg
$F link conv-stg conv-dim
$F link conv-stg conv-fact
$F link conv-dim conv-fact
$F link lineage conv-cl
$F link conv-fact conv-mart
$F link conv-cl conv-mart
$F link conv-mart validate
$F link validate report
step

# ════════════════════════════════════════════════════════════
# 二、扫描 + 解析
# ════════════════════════════════════════════════════════════
$F skill scan running --progress 30 --detail "枚举 QSYS / QGPL 成员"; step
$F skill scan running --progress 80 --detail "发现 118 个对象"; step
$F skill scan done --detail "118 个成员入库"
$F skill parse-dds running --progress 40 --detail "解析 DDS 记录格式"; step
$F skill parse-dds done --detail "字段级元数据完成"; step

# ════════════════════════════════════════════════════════════
# 三、血缘溯源：自底向上长出 4 层依赖树（含菱形）
# ════════════════════════════════════════════════════════════
$F skill lineage running --progress 10 --detail "锁定目标集市表"
$F set-target DM_SALES_PROFIT_MART; step

# —— 第 3 层：事实/维度 → 集市 ——
$F skill lineage running --progress 25 --detail "溯源集市直接上游"
$F add-node FCT_SALES     --type sql --feeds DM_SALES_PROFIT_MART
$F add-node FCT_INVENTORY --type sql --feeds DM_SALES_PROFIT_MART
$F add-node FCT_GL        --type sql --feeds DM_SALES_PROFIT_MART
$F add-node DIM_CUSTOMER  --type sql --feeds DM_SALES_PROFIT_MART,FCT_SALES,FCT_GL
$F add-node DIM_ITEM      --type sql --feeds FCT_SALES,FCT_INVENTORY
$F add-node DIM_DATE      --type sql --feeds FCT_SALES,FCT_INVENTORY,FCT_GL; step

# —— 第 2 层：清洗层 → 维度/事实 ——
$F skill lineage running --progress 50 --detail "溯源清洗层"
$F add-node STG_ORDERS    --type sql --feeds FCT_SALES,DIM_DATE
$F add-node STG_CUSTOMER  --type sql --feeds DIM_CUSTOMER
$F add-node STG_ITEM      --type sql --feeds DIM_ITEM
$F add-node STG_INVENTORY --type sql --feeds FCT_INVENTORY
$F add-node STG_GL        --type sql --feeds FCT_GL
$F add-node STG_EMPLOYEE  --type python --feeds FCT_GL; step

# —— 第 1 层：源物理文件/程序（菱形：共享源表喂多个清洗表）——
$F skill lineage running --progress 80 --detail "溯源到物理文件层"
$F add-node ORDHDR_PF  --type rpg --feeds STG_ORDERS
$F add-node ORDDTL_PF  --type rpg --feeds STG_ORDERS
$F add-node CUSTMAST_PF --type rpg --feeds STG_CUSTOMER,STG_EMPLOYEE
$F add-node REGION_PF  --type rpg --feeds STG_CUSTOMER,STG_EMPLOYEE
$F add-node ITEMMAST_PF --type rpg --feeds STG_ITEM,STG_INVENTORY
$F add-node PRICELST_PF --type rpg --feeds STG_ITEM
$F add-node INVTRANS_PF --type cobol --feeds STG_INVENTORY
$F add-node GLACCT_PF  --type rpg --feeds STG_GL
$F add-node POSTCL_CL  --type cl  --feeds STG_GL,STG_EMPLOYEE; step

$F skill lineage done --detail "22 节点 / 4 层依赖树构建完成"; step

# ════════════════════════════════════════════════════════════
# 四、按编号顺序（最远源头优先）逐层转换
# ════════════════════════════════════════════════════════════
run_node() {  # $1=id $2=detail_running $3=detail_done
  $F node "$1" running --progress 55 --detail "$2"; step
  $F node "$1" done --detail "$3"; step
}

# —— 源表层 ——
$F skill conv-source running --progress 10 --detail "从最远源头开始转换"; step
for n in ORDHDR_PF ORDDTL_PF CUSTMAST_PF REGION_PF ITEMMAST_PF PRICELST_PF GLACCT_PF; do
  $F node "$n" running --progress 60 --detail "DDS → CREATE TABLE"
  $F node "$n" done --detail "DDL 已生成"
  step
done
# COBOL / CL 走另一条 skill 分支
$F skill conv-cl running --progress 30 --detail "翻译 CL 调度逻辑"
$F node INVTRANS_PF running --progress 50 --detail "COBOL 拷贝簿 → schema"; step
$F node INVTRANS_PF done --detail "DDL 已生成"
$F node POSTCL_CL running --progress 60 --detail "CL → Airflow DAG 片段"; step
$F node POSTCL_CL done --detail "已生成 post_gl.py"
$F skill conv-cl done --detail "调度脚本完成"
$F skill conv-source done --detail "9 个源对象转换完成"; step

# —— 清洗层 ——
$F skill conv-stg running --progress 20 --detail "翻译清洗/去重逻辑"; step
run_node STG_ORDERS    "合并 ORDHDR+ORDDTL"      "已生成 stg_orders.sql"
run_node STG_CUSTOMER  "客户主数据清洗"          "已生成 stg_customer.sql"
run_node STG_ITEM      "物料+价目表关联"          "已生成 stg_item.sql"
run_node STG_INVENTORY "库存事务汇总"            "已生成 stg_inventory.sql"
run_node STG_GL        "总账过滤"                "已生成 stg_gl.sql"
run_node STG_EMPLOYEE  "员工区域清洗(pandas)"     "已生成 stg_employee.py"
$F skill conv-stg done --detail "6 个清洗表完成"; step

# —— 维度层 ——
$F skill conv-dim running --progress 30 --detail "构建缓变维 SCD2"; step
run_node DIM_CUSTOMER "客户维 SCD2"  "已生成 dim_customer.sql"
run_node DIM_ITEM     "物料维"        "已生成 dim_item.sql"
run_node DIM_DATE     "日期维生成"    "已生成 dim_date.sql"
$F skill conv-dim done --detail "3 个维度完成"; step

# —— 事实层（演示一次失败再恢复）——
$F skill conv-fact running --progress 30 --detail "构建事实表度量"; step
run_node FCT_SALES "销售事实 join 维度" "已生成 fct_sales.sql"
$F node FCT_INVENTORY running --progress 50 --detail "库存事实度量"; step
$F node FCT_INVENTORY error --detail "DIM_ITEM 键缺失 3 行"; step
$F node FCT_INVENTORY running --progress 85 --detail "补默认维成员后重跑"; step
$F node FCT_INVENTORY done --detail "已生成 fct_inventory.sql"; step
run_node FCT_GL "总账事实(部门×期间)" "已生成 fct_gl.sql"
$F skill conv-fact done --detail "3 个事实表完成"; step

# —— 集市层 ——
$F skill conv-mart running --progress 50 --detail "拼装利润集市宽表"; step
run_node DM_SALES_PROFIT_MART "汇聚销售/库存/总账+客户维" "已生成 dm_sales_profit_mart.sql"
$F skill conv-mart done --detail "集市宽表完成"; step

# ════════════════════════════════════════════════════════════
# 五、校验 + 报告
# ════════════════════════════════════════════════════════════
$F skill validate running --progress 35 --detail "逐层比对行数/金额"; step
$F skill validate running --progress 70 --detail "校验集市层利润口径"; step
$F skill validate done --detail "全链路校验通过"; step
$F skill report running --progress 60 --detail "汇总 22 对象迁移结果"; step
$F skill report done --detail "已输出 mart_migration_report.md"

echo "[simulate-complex] 完成"
