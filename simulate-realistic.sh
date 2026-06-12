#!/usr/bin/env bash
# Realistic simulation: the agent does NOT know the lineage up front.
# It starts at the target table and traces dependencies on the fly (post-order DFS):
#   read a node's source -> discover its upstreams (nodes appear) -> recurse up to the
#   leaf sources -> convert sources first -> bubble conversions back down to the target.
# Skills light up reactively as the agent decides which one to call for each object type.
set -e
cd "$(dirname "$0")"
F="python3 flowctl.py"
S=${1:-1.5}            # seconds per step
step() { sleep "$S"; }
SK=" "                 # tracks which skills have been started

# Ensure a skill is running; register name + dependency edge only on first call.
sk() { # id name detail [from]
  if [[ "$SK" != *" $1 "* ]]; then
    $F skill "$1" running --name "$2" --detail "$3"
    [ -n "$4" ] && $F link "$4" "$1"
    SK="$SK$1 "
  else
    $F skill "$1" running --detail "$3"
  fi
}

# The agent reads a node's source to find its upstreams (the "trace" skill at work).
vis() { # node detail
  $F skill trace running --detail "Analyzing $1"
  $F node "$1" running --progress 20 --detail "${2:-Parsing dependencies}"
  step
}
queued() { $F node "$1" pending --detail "Queued for conversion"; }

# Convert one object; the chosen skill is invoked reactively.
conv() { # node skill sname sfrom detail_run detail_done
  sk "$2" "$3" "Converting $1" "$4"
  $F node "$1" running --progress 60 --detail "$5"
  step
  $F node "$1" done --detail "$6"
}

# ════════════════════════════════════════════════════════════
$F reset all
$F title "Sales Profit Data Mart — live AS/400 migration"

# ── Inventory the library, then start tracing from the target ──
sk scan "Scan AS/400 library" "Enumerating QSYS / QGPL"; step
$F skill scan running --progress 70 --detail "118 objects found"; step
$F skill scan done --detail "118 members catalogued"
sk parse-dds "Parse DDS / fields" "Reading record formats" scan; step
$F skill parse-dds done --detail "Field metadata ready"
sk trace "Lineage traceback" "Locating target table" parse-dds
$F set-target DM_SALES_PROFIT_MART; step

# ════════════════════════════════════════════════════════════
# Post-order DFS from the target. Nodes appear only when their child is read.
# ════════════════════════════════════════════════════════════

# read the mart -> discover its direct inputs
vis DM_SALES_PROFIT_MART "Reading mart SQL"
$F add-node FCT_SALES     --type sql --feeds DM_SALES_PROFIT_MART
$F add-node FCT_INVENTORY --type sql --feeds DM_SALES_PROFIT_MART
$F add-node FCT_GL        --type sql --feeds DM_SALES_PROFIT_MART
$F add-node DIM_CUSTOMER  --type sql --feeds DM_SALES_PROFIT_MART
queued DM_SALES_PROFIT_MART

# ── branch: FCT_SALES ──
vis FCT_SALES "Reading fct_sales joins"
$F add-node STG_ORDERS   --type sql --feeds FCT_SALES
$F add-node DIM_CUSTOMER --type sql --feeds FCT_SALES
$F add-node DIM_ITEM     --type sql --feeds FCT_SALES
$F add-node DIM_DATE     --type sql --feeds FCT_SALES
queued FCT_SALES

vis STG_ORDERS "Reading staging transform"
$F add-node ORDHDR_PF --type rpg --feeds STG_ORDERS
$F add-node ORDDTL_PF --type rpg --feeds STG_ORDERS
queued STG_ORDERS
# reached leaf sources -> convert them first
conv ORDHDR_PF conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
conv ORDDTL_PF conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
conv STG_ORDERS conv-stg "Staging → SQL" conv-source "Merge header + lines" "Generated stg_orders.sql"

vis DIM_CUSTOMER "Reading SCD2 logic"
$F add-node STG_CUSTOMER --type sql --feeds DIM_CUSTOMER
queued DIM_CUSTOMER
vis STG_CUSTOMER "Reading staging transform"
$F add-node CUSTMAST_PF --type rpg --feeds STG_CUSTOMER
$F add-node REGION_PF   --type rpg --feeds STG_CUSTOMER
queued STG_CUSTOMER
conv CUSTMAST_PF conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
conv REGION_PF   conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
conv STG_CUSTOMER conv-stg "Staging → SQL" conv-source "Cleanse customer master" "Generated stg_customer.sql"
conv DIM_CUSTOMER conv-dim "Dimensions → SQL" conv-stg "Build customer SCD2" "Generated dim_customer.sql"

vis DIM_ITEM "Reading item dimension"
$F add-node STG_ITEM --type sql --feeds DIM_ITEM
queued DIM_ITEM
vis STG_ITEM "Reading staging transform"
$F add-node ITEMMAST_PF --type rpg --feeds STG_ITEM
$F add-node PRICELST_PF --type rpg --feeds STG_ITEM
queued STG_ITEM
conv ITEMMAST_PF conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
conv PRICELST_PF conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
conv STG_ITEM conv-stg "Staging → SQL" conv-source "Join item + price list" "Generated stg_item.sql"
conv DIM_ITEM conv-dim "Dimensions → SQL" conv-stg "Build item dimension" "Generated dim_item.sql"

vis DIM_DATE "Deriving date grain from orders"
$F add-node STG_ORDERS --type sql --feeds DIM_DATE
queued DIM_DATE
conv DIM_DATE conv-dim "Dimensions → SQL" conv-stg "Generate calendar grain" "Generated dim_date.sql"

conv FCT_SALES conv-fact "Facts → SQL" conv-dim "Join measures to dims" "Generated fct_sales.sql"

# ── branch: FCT_INVENTORY (diamond: reuses ITEMMAST / DIM_ITEM / DIM_DATE) ──
vis FCT_INVENTORY "Reading inventory fact"
$F add-node STG_INVENTORY --type sql --feeds FCT_INVENTORY
$F add-node DIM_ITEM      --type sql --feeds FCT_INVENTORY
$F add-node DIM_DATE      --type sql --feeds FCT_INVENTORY
queued FCT_INVENTORY
vis STG_INVENTORY "Reading staging transform"
$F add-node INVTRANS_PF --type cobol --feeds STG_INVENTORY
$F add-node ITEMMAST_PF --type rpg   --feeds STG_INVENTORY
queued STG_INVENTORY
conv INVTRANS_PF conv-source "RPG/DDS → DDL" trace "Copybook → schema" "DDL generated"
conv STG_INVENTORY conv-stg "Staging → SQL" conv-source "Summarise inventory txns" "Generated stg_inventory.sql"
# fact build hits a data issue, then recovers
sk conv-fact "Facts → SQL" "Converting FCT_INVENTORY" conv-dim
$F node FCT_INVENTORY running --progress 50 --detail "Inventory measures"; step
$F node FCT_INVENTORY error --detail "DIM_ITEM key missing (3 rows)"; step
$F node FCT_INVENTORY running --progress 85 --detail "Added default member, retry"; step
$F node FCT_INVENTORY done --detail "Generated fct_inventory.sql"; step

# ── branch: FCT_GL ──
vis FCT_GL "Reading GL fact"
$F add-node STG_GL       --type sql    --feeds FCT_GL
$F add-node STG_EMPLOYEE --type python --feeds FCT_GL
$F add-node DIM_CUSTOMER --type sql    --feeds FCT_GL
$F add-node DIM_DATE     --type sql    --feeds FCT_GL
queued FCT_GL
vis STG_GL "Reading staging transform"
$F add-node GLACCT_PF --type rpg --feeds STG_GL
queued STG_GL
conv GLACCT_PF conv-source "RPG/DDS → DDL" trace "DDS → CREATE TABLE" "DDL generated"
$F skill conv-source done --detail "9 source objects → DDL"
conv STG_GL conv-stg "Staging → SQL" conv-source "Filter posted GL" "Generated stg_gl.sql"

vis STG_EMPLOYEE "Reading employee cleanse job"
$F add-node CUSTMAST_PF --type rpg    --feeds STG_EMPLOYEE
$F add-node REGION_PF   --type rpg    --feeds STG_EMPLOYEE
$F add-node POSTCL_CL   --type cl     --feeds STG_EMPLOYEE
queued STG_EMPLOYEE
# whole tree is now discovered
$F skill trace done --detail "22-node lineage resolved"
conv POSTCL_CL conv-cl "CL jobs → Python" trace "CL → Airflow DAG" "Generated post_gl.py"
conv STG_EMPLOYEE conv-cl "CL jobs → Python" conv-cl "Pandas cleanse (region)" "Generated stg_employee.py"
$F skill conv-cl done --detail "Scheduling scripts ready"
$F skill conv-stg done --detail "6 staging tables ready"
conv FCT_GL conv-fact "Facts → SQL" conv-dim "GL by dept × period" "Generated fct_gl.sql"
$F skill conv-dim done --detail "3 dimensions ready"
$F skill conv-fact done --detail "3 fact tables ready"

# ── finally the target itself ──
conv DM_SALES_PROFIT_MART conv-mart "Mart → SQL" conv-fact "Assemble profit wide table" "Generated dm_sales_profit_mart.sql"
$F skill conv-mart done --detail "Mart table ready"

# ── validate + report ──
sk validate "Full-chain validation" "Reconciling row counts" conv-mart; step
$F skill validate running --progress 70 --detail "Checking profit semantics"; step
$F skill validate done --detail "All layers reconciled"
sk report "Migration report" "Summarising 22 objects" validate; step
$F skill report done --detail "Wrote mart_migration_report.md"

echo "[simulate-realistic] done"
