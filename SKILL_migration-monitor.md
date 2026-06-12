---
name: migration-monitor
description: >
  Emit live progress to the local AS/400 Migration Monitor dashboard while migrating
  AS/400 (RPG / CL / COBOL / DDS) code to SQL and Python. Drives the Skill Pipeline view
  and the ETL Lineage tree via the bundled flowctl.py CLI.
---

# Migration Monitor — reporting skill

You are running one step of a larger AS/400 → SQL/Python migration. A local dashboard
(`skillflow-monitor`, a React Flow app) renders your progress in real time by polling
two JSON files every second. Your job in THIS skill is to **report status as you work**
by invoking `flowctl.py`. The dashboard updates automatically — never edit the JSON files
by hand, never touch the React/UI code.

## Configuration

- `MONITOR_DIR` = absolute path to the `skillflow-monitor` folder.
  Default: `/Users/dailu/soft/airflow/skillflow-monitor`
- All commands below are: `python3 "$MONITOR_DIR/flowctl.py" <args>`
- The dashboard runs at `http://localhost:5174/` (start it with `npm run dev` in `MONITOR_DIR`).

## Two views you report into

1. **Skill Pipeline** — one node per skill/task in the migration run, wired by dependency
   edges. Use it to show *which skill is running now*.
2. **ETL Lineage** — the dependency tree of one target table. Nodes are data objects
   (physical files, programs, staging/dim/fact/mart tables). The dashboard auto-numbers
   nodes by distance from the target: **the most upstream source is `#1`**, the target
   table has the highest number and a `TARGET` badge. This mirrors the order you should
   convert in (sources first).

## Status values

`pending` · `running` · `done` · `error` · `skipped`

## Node types (drive the colored type chip)

`rpg` · `cl` · `cobol` · `sql` · `python` · `table` · `view` · `file`

---

## Command reference

### Skill Pipeline

```bash
# Register / start a skill (auto-creates if new)
python3 "$MONITOR_DIR/flowctl.py" skill <skill-id> running \
  --name "Human readable name" --detail "What it is doing right now"

# Update progress (0-100) as the skill advances
python3 "$MONITOR_DIR/flowctl.py" skill <skill-id> running --progress 60 --detail "..."

# Finish / fail
python3 "$MONITOR_DIR/flowctl.py" skill <skill-id> done  --detail "Result summary"
python3 "$MONITOR_DIR/flowctl.py" skill <skill-id> error --detail "Why it failed"

# Wire dependency edges between skills (arrow source -> target)
python3 "$MONITOR_DIR/flowctl.py" link <upstream-skill-id> <downstream-skill-id>
```

### ETL Lineage

```bash
# Declare the target table of the lineage tree (do this once, first)
python3 "$MONITOR_DIR/flowctl.py" set-target <TARGET_TABLE>

# Register an object as you discover it during traceback.
# --feeds lists its DOWNSTREAM consumers (comma-separated); missing ones are auto-created.
python3 "$MONITOR_DIR/flowctl.py" add-node <OBJECT> --type rpg --feeds <DOWNSTREAM_A>,<DOWNSTREAM_B>

# Convert an object: mark running with progress, then done/error
python3 "$MONITOR_DIR/flowctl.py" node <OBJECT> running --progress 50 --detail "DDS -> CREATE TABLE"
python3 "$MONITOR_DIR/flowctl.py" node <OBJECT> done  --detail "Generated stg_orders.sql"
python3 "$MONITOR_DIR/flowctl.py" node <OBJECT> error --detail "Missing dimension key"
```

### Run-level controls

```bash
python3 "$MONITOR_DIR/flowctl.py" reset all          # clear both views before a new run
python3 "$MONITOR_DIR/flowctl.py" title "ORDR series migration"   # dashboard title
```

---

## Required reporting protocol (follow exactly)

**A. Pipeline reporting — every skill must do this:**

1. On start:
   `skill <skill-id> running --name "<name>" --detail "<starting note>"`
2. At each meaningful milestone, update `--progress` and `--detail`.
3. On success: `skill <skill-id> done --detail "<summary>"`.
   On failure: `skill <skill-id> error --detail "<reason>"` — then stop and surface the error.
4. If this skill depends on another, declare it once with `link <upstream> <this>`.

**B. Lineage reporting — any skill that traces or converts ETL must also do this:**

5. Once the target table is known: `set-target <TARGET>` (once per run).
6. For **each** upstream object you discover during traceback, immediately:
   `add-node <OBJECT> --type <type> --feeds <its downstream object(s)>`
   Add nodes bottom-up or top-down — edges connect either way as long as `--feeds` points
   at the *downstream* consumer.
7. Convert in lineage order (`#1` first = most upstream source). For each object:
   `node <OBJECT> running --progress <pct> --detail "<what you're translating>"` then
   `node <OBJECT> done --detail "<artifact produced>"`.

**C. New run hygiene:** the entry/orchestrator skill runs `reset all` and `title "..."`
once before any sub-skill reports.

## Rules

- Report **before** and **after** each unit of work, not only at the end — the value is the
  live animation. A long step with no `--progress` update looks stuck.
- Do not invent objects; only add nodes that exist in the source you actually traced.
- `--detail` is shown verbatim on the card. Keep it short (≤ ~40 chars), present tense
  while running ("Translating GROUP BY"), past tense when done ("Generated fct_sales.sql").
- Never write to `public/status/*.json` directly and never modify files under `src/`.
- If `flowctl.py` errors, fix the arguments — do not silently skip reporting.

## Worked example (small lineage)

```bash
MON="/Users/dailu/soft/airflow/skillflow-monitor/flowctl.py"
python3 "$MON" reset all
python3 "$MON" title "Sales summary migration"

# pipeline
python3 "$MON" skill trace   running --name "Lineage traceback" --detail "Resolving target"
python3 "$MON" set-target RPT_SALES_SUMMARY
python3 "$MON" add-node STG_ORDERS  --type sql --feeds RPT_SALES_SUMMARY
python3 "$MON" add-node ORDERS_PF   --type rpg --feeds STG_ORDERS
python3 "$MON" add-node ORDLINES_PF --type rpg --feeds STG_ORDERS
python3 "$MON" skill trace done --detail "3-node tree built"

python3 "$MON" skill convert running --name "RPG -> SQL" --detail "Starting at source"
python3 "$MON" node ORDERS_PF   running --progress 50 --detail "DDS -> DDL"
python3 "$MON" node ORDERS_PF   done    --detail "DDL generated"
python3 "$MON" node ORDLINES_PF done    --detail "DDL generated"
python3 "$MON" node STG_ORDERS  running --progress 60 --detail "Merge headers + lines"
python3 "$MON" node STG_ORDERS  done    --detail "Generated stg_orders.sql"
python3 "$MON" node RPT_SALES_SUMMARY done --detail "Generated rpt_sales_summary.sql"
python3 "$MON" skill convert done --detail "All objects converted"
```
