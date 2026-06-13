# AS400 → Java 迁移对等性对比脚手架

一套**人机协同**框架:10 人在 **Windows + VS Code + GitHub Copilot Agent 模式**里,逐单元判定 Java 重写是否与 AS400 旧系统**行为一致(迁移对等性)**,并枚举"还有多少行为差异"。
**没有 Copilot CLI**——LLM 步骤全靠人在 agent 里手动驱动(skill + `/` prompt 入口),确定性活由协调人离线跑 **Python**。

- 旧系统:AS400 / IBM i,约 3200 万行(RPG III/IV、RPGLE、CL、COBOL、DDS、显示文件、嵌入式 SQL)
- 新系统:Java 重写,约 480 万行
- 本仓库**不做业务代码分析**,只提供脚手架:方法论、schema、离线 Python 工具、skill/prompt、协同纪律、最小样例。

> ⚠ **VS Code 版本确认**:`.github/skills/**/SKILL.md` 由 Copilot agent 模式自 **2026-04** 起支持。请团队在 README 里核对本机 VS Code 版本。**若暂不支持 SKILL.md,用 `.github/prompts/*.prompt.md` 的 `/<step>` 入口照样能跑**,skill 只是把方法整理得更顺、能渐进加载参考资料。

## 它怎么工作(5 步流水线)
```
extract-semantics → align-mapping → compare-pair → generate-difftests → propagate-pattern
   两侧各抽语义        锚点对齐分桶     规则级 diff      运行时 oracle 规格     根因横扫 N/M
```
每步 = 一个 skill(`.github/skills/`)+ 一个 `/` prompt 入口(`.github/prompts/`);每步产物有 JSON schema;**不过 schema 不算完成**。协调人离线用 `tools/*.py` 建题、分配、校验、汇总。

核心红线:**语义匹配 ≠ 行为一致**。语义看一致最多产 `candidate_equivalent`,**绝不直接判 equivalent**;定论来自规则级 diff + 运行时差异测试。

## 目录结构
```
.github/
  copilot-instructions.md         # always-on 方法论 + 协同纪律
  skills/<step>/SKILL.md          # 5 个 skill(compare-pair 内置缺陷类清单)
  prompts/<step>.prompt.md        # 5 个 / 显式入口(mode: agent)
  agents/parity-analyzer.agent.md # 只读分析 persona,只许写 analysis/
schemas/                          # 7 个 JSON schema(产物合同)
tools/                            # 全部 Python,协调人离线跑(含锚点适配器/验AI/建索引)
java-extractor/                   # Maven 项目:JavaParser+JSqlParser 抽 Java 锚点
docs/                             # METHODOLOGY / GLOSSARY / DEFECT-CLASSES / RUNBOOK / ANCHORS
analysis/                         # 全部产物落这里(语义/对齐/diff/测试/qa/索引/分配/进度)
samples/                          # 最小样例(RPG/Java 配对 + 锚点导出 + units/assignments)
```

## 快速开始(协调人)
```bat
:: 1. 装环境(Windows;路径含空格/中文 OK)
python -m venv .venv
.venv\Scripts\activate
pip install -r tools\requirements.txt

:: 2. 抽锚点 —— 推荐用免费的权威来源(详见 docs/ANCHORS.md),不用商业工具
::    AS400: IBM i 平台交叉引用导出
python tools\ingest_ibmi_metadata.py --dsppgmref samples\ibmi_exports\dsppgmref.csv --dspffd samples\ibmi_exports\dspffd.csv --src samples\as400 --out analysis\anchors.as400.json
::    Java: JavaParser/JSqlParser(java-extractor)产出后归一
python tools\ingest_java_anchors.py --in samples\java_extract\java-anchors.raw.json --out analysis\anchors.java.json
::    (兜底)没有上述来源时,正则 best-effort: python tools\extract_anchors.py --src ... --side ... --out ...

:: 3. 切单元 + 分配 10 人
python tools\build_units.py --anchors analysis\anchors.as400.json analysis\anchors.java.json --out analysis\units.csv
python tools\assign_work.py --units analysis\units.csv --names 张三,李四,王五 --out analysis\assignments

:: 4. (成员干完后)校验 + 验 AI + 地图 + 进度 + 汇总
python tools\validate_outputs.py --path analysis
python tools\verify_semantics.py --semantics analysis\semantics --anchors analysis\anchors.as400.json analysis\anchors.java.json --out analysis\qa
python tools\build_index.py --semantics analysis\semantics --out analysis
python tools\progress.py --assignments analysis\assignments --out analysis\PROGRESS.md
python tools\aggregate_matrix.py --analysis analysis --out analysis\parity_matrix.json
```

> **锚点准确度 + 用锚点验证 AI + 代码地图 + 分阶段(先 Java 后 AS400)**:见 [docs/ANCHORS.md](docs/ANCHORS.md)。
> `verify_semantics.py` 用确定性锚点抓 LLM 幻觉(`suspect` 非零退出可卡 CI);`build_index.py` 产出"表→单元"的代码地图,支持"先递推索引、需要时再下钻源码"。

## 快速开始(成员,在 Copilot Agent 模式)
1. 打开 `analysis/assignments/<你的名字>.csv`,找下一个产物还不存在的单元。
2. **新建一个 Chat**(选 `parity-analyzer` agent),打开该单元源文件。
3. 输入 `/extract-semantics`(或当前阶段对应的 `/` 命令)。
4. agent 产出 JSON 后自检:`python tools\validate_outputs.py --file <产物> --schema <名>`。
5. **关掉 Chat**,下一个单元再开新的——**每单元独立会话,绝不串上下文**。

详细操作见 [docs/RUNBOOK.md](docs/RUNBOOK.md)。方法论见 [docs/METHODOLOGY.md](docs/METHODOLOGY.md),缺陷类清单见 [docs/DEFECT-CLASSES.md](docs/DEFECT-CLASSES.md)。

## 重要前提与边界
- **extract_anchors.py 是 best-effort 正则**,对 RPG(尤其定宽列)抽取不完整、无法可靠抽字段名。生产请接 **Fresche X-Analysis / ARCAD / IBM ADDI** 导出权威锚点。
- **EBCDIC/codepage 源码**:工具读不了的非 UTF-8 文件会**告警跳过**,不崩;需专业工具转码或导出。
- **agent 只写 `analysis/`**,不碰源码/schema/tools。
- 本脚手架**不假装做真实代码分析**;`samples/` 仅为端到端演示。

## 最小样例端到端演示
见 [samples/README.md](samples/README.md):2 对 RPG/Java 片段 + 一份 units/assignments,演示一个成员在 agent 里跑 `/extract-semantics → /compare-pair`,以及协调人跑 `aggregate_matrix.py` 的输出样子。
