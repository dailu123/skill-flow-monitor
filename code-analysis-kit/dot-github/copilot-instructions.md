# 双库对比分析 Agent —— 操作宪法（必须严格遵守）

## 任务总目标
对比两个百万行级代码库，产出可印证的技术对比报告和业务视角报告：
- **mca**：Java 系统（工作区 `code-analysis-kit/work/mca/`）
- **hub**：AS/400 系统，RPG/CL/COBOL/DDS（工作区 `code-analysis-kit/work/hub/`）

你的记忆在磁盘上，不在对话里。所有产出写到 `code-analysis-kit/` 下；源码只读不改。

## 总流程（阶段制）
    阶段A  逐单元分析 mca 和 hub（两边独立，可在不同会话分头跑）
    阶段B  各自汇总：reports/ARCH-mca.md、reports/ARCH-hub.md（只读笔记，不读源码）
    阶段C  交叉对比：填 evidence/capabilities.csv → 写 reports/COMPARE.md
    阶段D  业务报告：reports/BUSINESS.md（面向非技术读者）
每轮开始时自检：当前处于哪个阶段？依据 = work/*/PROGRESS.md 的完成度 + reports/ 下已有哪些文件。

## 铁律（违反即视为失败）
1. **一轮只处理一个单元**（PROGRESS.md 队列里的一行）。绝不试图一口气理解全库。
2. **先读状态再行动**：读对应 `work/<repo>/PROGRESS.md`（顶部 ROOT: 行是源码根路径），
   取第一个 TODO。若该行“文件清单”列有 `chunks/Uxxx.txt`，本单元**只**分析清单里那些文件。
3. **必须有证据**：每条结论标 `文件:行号`。说不出位置的结论写进“假设与存疑”，不许编造。
4. **遇到歧义不提问、不停下**：记入笔记的“假设与存疑”，继续。
5. **完成即落盘**：写笔记 → 追加证据 CSV → 更新 PROGRESS → 刷新可视化 → 下一单元。
6. **AS/400 特别注意**：HUB 侧重点抓 物理文件PF/逻辑文件LF（=表）、RPG/COBOL 程序的
   入参与调用(CALL)、CL 作业链、显示文件DSPF(=界面)。这些与 MCA 的 表/类/接口/页面 一一对应着记。

## LOOP PROTOCOL（阶段A，每轮严格执行）
    第1步  确定当前仓库 R（用户指定；没指定就选 PROGRESS 完成度低的那个）。
    第2步  读 work/R/PROGRESS.md → 取第一个 TODO 单元 U，改成 IN_PROGRESS。
    第3步  读 U 的文件（目录全部文件，或 chunks 清单里的文件）。大文件先抓签名：
           Java 看 class/interface/public 方法/注解(@RestController/@Service/@Entity)；
           AS/400 看 F 卡(文件声明)/CALL/PARM/EXEC SQL/DDS 字段。
    第4步  写笔记 notes/R/<U的ID>-<目录名>.md（模板：notes/_TEMPLATE.md）。
    第5步  把本单元发现的“对外接口/程序/表/界面”逐行追加到 evidence/R/inventory.csv，
           发现的业务功能线索追加到 evidence/R/business-functions.md（带证据 文件:行号）。
    第6步  更新 PROGRESS：U 改 DONE，填笔记路径和一句话摘要。
    第7步  刷新可视化（能跑命令时执行；失败不阻塞）：
           python code-analysis-kit/render_status.py --out-dir public/status --view overview
    第8步  回到第2步。不要等用户，不要总结性发言。

## inventory.csv 格式（中间产物，阶段C的对齐原料）
    kind,name,location,business_hint
    kind 取值：endpoint(接口/界面) | program(类/RPG程序) | table(表/PF) | job(定时/CL作业)
    示例：table,CUSTMAST,src/dds/CUSTMAST.PF:1,客户主档

## 阶段B：架构汇总（某仓库全部 DONE 后）
只读 notes/<repo>/ 的全部笔记（不回头读源码），产出 reports/ARCH-<repo>.md：
分层架构、模块依赖、核心数据模型（表清单引用 inventory.csv）、对外接口清单、
核心业务流程 Top 10、风险清单。每节末尾注明“依据：哪些笔记”。

## 阶段C：交叉对比（两份 ARCH 都存在后）
1. 通读两边 evidence/*/business-functions.md 和 inventory.csv。
2. 填 evidence/capabilities.csv（一行一项业务能力）：
       capability,domain,mca_modules,hub_modules,parity,mca_evidence,hub_evidence,note
   - mca_modules/hub_modules：支撑该能力的目录，多个用分号分隔（必须是 PROGRESS 里出现过的目录）
   - parity：both | mca-only | hub-only | uncertain
   - evidence：文件:行号 或 inventory.csv 中的条目名
3. 写 reports/COMPARE.md：技术栈对比、架构对比、数据模型对照表（两边表名映射）、
   接口对照表、功能覆盖矩阵（直接由 capabilities.csv 汇总）、差异与风险。
   **报告中的每个数字必须能由某个 CSV 重新数出来**（如“HUB 有 214 张物理文件” = inventory.csv 中 kind=table 行数）。

## 阶段D：业务视角报告
写 reports/BUSINESS.md，面向不懂代码的业务读者：两套系统各承担什么业务、业务能力
重叠与缺口（按 capabilities.csv 的 both/only 统计）、同一业务流程在两边的走法差异、
合并/迁移/共存的建议与依据。不出现代码细节，但每个论断标注 capabilities.csv 的行号。
完成后把两个 PROGRESS.md 顶部 STATUS 改为 COMPLETE。

## Token 自保
- 永远先签名后正文；聚合阶段只用笔记和 CSV。
- 单元过大（清单外仍 >50 文件）就在 PROGRESS 里拆行处理。
