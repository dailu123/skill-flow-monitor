# SkillFlow Monitor — AS400 迁移本地可视化

本地实时监控两个视图（浏览器内切换 Tab）：

1. **🤖 Skill 流水线** — 你的一系列 skill 谁在跑、跑到哪、成功还是失败
2. **🌳 ETL 血缘溯源** — 从目标表向上溯源的依赖树，离目标最远的源头节点编号为 **1**（即 AI 的处理顺序），目标表带 🎯 标记

技术栈：**React Flow（@xyflow/react）** 流程图组件库 + **dagre** 自动布局 + Vite。
动效：进行中节点有**呼吸光圈 + 旋转 spinner + 流光进度条**；指向进行中节点的连线有**青色流动虚线 + 沿线移动的光点**；完成的节点/连线变绿，失败变红。

## 快速开始

```bash
cd skillflow-monitor
npm install
npm run dev        # 自动打开 http://localhost:5173
```

打开后立即能看到内置示例数据的完整动效。UI **每秒轮询** `public/status/*.json`，文件一变界面就变，无需刷新浏览器。

## 工作原理

```
你的 skill ──调用──▶ flowctl.py ──原子写入──▶ public/status/*.json ◀──每秒轮询── 浏览器 UI
```

skill 只需要在关键时刻调用 `flowctl.py`（纯 Python 标准库，无依赖）。不存在的 skill/节点会**自动创建**，所以不需要预先注册。

## flowctl.py 命令速查

| 场景 | 命令 |
|---|---|
| skill 开始 | `python flowctl.py skill <id> running --name "中文名" --detail "说明"` |
| skill 汇报进度 | `python flowctl.py skill <id> running --progress 60 --detail "..."` |
| skill 完成 / 失败 | `python flowctl.py skill <id> done` / `... error --detail "原因"` |
| skill 连线 | `python flowctl.py link <上游id> <下游id>` |
| 设置血缘目标表 | `python flowctl.py set-target RPT_SALES_SUMMARY` |
| 溯源发现上游表 | `python flowctl.py add-node ORDERS_PF --type rpg --feeds STG_ORDERS_AGG` |
| 节点开始转换 | `python flowctl.py node ORDERS_PF running --progress 30 --detail "翻译中"` |
| 节点完成 | `python flowctl.py node ORDERS_PF done` |
| 新一轮迁移前清空 | `python flowctl.py reset all` |
| 设置页面标题 | `python flowctl.py title "ORDR 系列迁移"` |

- 状态：`pending` `running` `done` `error` `skipped`
- 节点类型（决定图标）：`table` 🗄️ `view` 👁️ `file` 📄 `rpg` ⚙️ `cl` 📜 `cobol` 🏛️ `sql` 🧮 `python` 🐍
- 环境变量 `FLOW_STATUS_DIR` 可把状态文件指到别处（UI 仍读 `public/status`，一般不用改）

## 套用到你已有的 skill（直接复制这段进 skill 的 markdown）

> 把 `<MONITOR>` 换成本目录的绝对路径，`<skill-id>` 换成该 skill 的英文 id。

```markdown
## 可视化埋点（每一步都必须执行，不得省略）

本 skill 运行期间必须通过以下命令上报状态，供本地监控页面展示：

1. skill 开始时：
   `python <MONITOR>/flowctl.py skill <skill-id> running --name "<skill 中文名>" --detail "<当前在做什么>"`
2. 每完成一个阶段性步骤，更新进度（progress 为 0-100 的估算值）：
   `python <MONITOR>/flowctl.py skill <skill-id> running --progress <pct> --detail "<当前在做什么>"`
3. 全部完成时：`python <MONITOR>/flowctl.py skill <skill-id> done --detail "<结果摘要>"`
   失败时：`python <MONITOR>/flowctl.py skill <skill-id> error --detail "<失败原因>"`

如果本 skill 涉及 ETL 血缘分析或代码转换，还须上报血缘树：

4. 确定目标表后：`python <MONITOR>/flowctl.py set-target <目标表名>`
5. 每溯源到一个上游对象（物理文件/逻辑文件/RPG 程序等），立刻登记：
   `python <MONITOR>/flowctl.py add-node <对象名> --type <rpg|table|sql|python|cl|cobol> --feeds <它的下游对象名>`
6. 开始转换某个对象时：`python <MONITOR>/flowctl.py node <对象名> running --progress <pct> --detail "<转换说明>"`
   该对象转换完成：`python <MONITOR>/flowctl.py node <对象名> done --detail "<产物，如 已生成 stg_orders.sql>"`
   失败：`python <MONITOR>/flowctl.py node <对象名> error --detail "<原因>"`
```

整条流水线开跑前，由你的入口 skill（或你手动）执行一次：

```bash
python <MONITOR>/flowctl.py reset all
python <MONITOR>/flowctl.py title "本轮迁移的名字"
# 如果 skill 之间有先后依赖，登记连线（也可以让各 skill 自己 link）：
python <MONITOR>/flowctl.py link scan lineage
python <MONITOR>/flowctl.py link lineage convert-sql
```

## JSON 契约（让 Copilot 改 UI 或直接写文件时参考）

`public/status/pipeline.json`：

```json
{
  "title": "页面标题",
  "skills": [
    { "id": "convert-sql", "name": "RPG → SQL 转换", "status": "running",
      "progress": 65, "detail": "正在转换 STG_ORDERS_AGG" }
  ],
  "edges": [ { "from": "scan", "to": "convert-sql" } ]
}
```

`public/status/lineage.json`（编号由 UI 根据离 `target` 的距离自动计算，最远 = 1）：

```json
{
  "target": "RPT_SALES_SUMMARY",
  "nodes": [
    { "id": "ORDERS_PF", "label": "ORDERS_PF", "type": "rpg",
      "status": "done", "progress": 100, "detail": "DDS 解析完成" }
  ],
  "edges": [ { "from": "ORDERS_PF", "to": "STG_ORDERS_AGG" } ]
}
```

## 让 Copilot 修改这个模板

把整个 `skillflow-monitor/` 目录给 Copilot，并告诉它：

- UI 入口在 `src/App.jsx`，节点卡片样式在 `src/StatusNode.jsx` + `src/theme.css`，连线动效在 `src/FlowingEdge.jsx`，布局与编号算法在 `src/layout.js`
- 数据契约见本 README「JSON 契约」一节，**改 UI 不要破坏契约**；要加新字段时同时更新 `flowctl.py` 和本节文档
- 图标/状态文案集中在 `StatusNode.jsx` 顶部的 `ICONS` / `STATUS_TEXT` 常量，配色集中在 `theme.css` 的 `:root` 变量

## 常见调整

- **轮询频率**：`src/App.jsx` 中 `usePoll(url, ms = 1000)` 的默认值
- **布局方向/间距**：`src/layout.js` 中 `rankdir / ranksep / nodesep`
- **新增节点类型图标**：`src/StatusNode.jsx` 的 `ICONS`
