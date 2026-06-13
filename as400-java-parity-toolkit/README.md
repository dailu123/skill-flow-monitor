# AS400 → Java 迁移对等性对比脚手架

判定 Java 重写是否与 AS400 旧系统**行为一致**,并枚举"还剩多少行为差异"。
做法:**确定性的活(抽锚点、切单元、校验、汇总)用 Python 离线跑;模糊的活(读懂语义、对比行为)由人在 VS Code Copilot Agent 模式里逐单元驱动。** 没有 Copilot CLI。

- 旧系统:AS400 / IBM i(RPG/CL/COBOL/DDS/嵌入式 SQL),约 3200 万行
- 新系统:Java 重写,约 480 万行
- 本仓库只是**脚手架**(方法、工具、schema、协同纪律、样例),不含真实业务分析。

**核心红线:语义看着一样 ≠ 行为一致。** 语义匹配最多产 `candidate_equivalent`,绝不直接判 `equivalent`;定论来自规则级 diff + 运行时差异测试。

---

## 0. 角色与前置

| 角色 | 干什么 | 需要装什么 |
| --- | --- | --- |
| **协调人**(1 人) | 离线跑 Python:抽锚点 → 切单元 → 分配 → 校验/验AI/汇总 | Python 3.10+;(抽 Java 锚点)JDK 17 + Maven;(抽 AS400 锚点)能登录 IBM i |
| **成员**(10 人) | 在 Copilot Agent 里逐单元跑 `/` 命令产出 JSON | VS Code + GitHub Copilot |

> ⚠ VS Code 需支持 `.github/skills/**/SKILL.md`(Copilot agent 模式 2026-04 起)。**不支持也能用** `.github/prompts/*.prompt.md` 的 `/<step>` 入口照跑,skill 只是更顺。

装 Python 环境(协调人,一次性):
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |  macOS/Linux: source .venv/bin/activate
pip install -r tools/requirements.txt
```

---

## 1. 先用样例把整条链路跑通(5 分钟,强烈建议先做)

仓库自带 2 对 RPG/Java 样例和现成产物,照抄即可看到全流程结果:
```bash
# 1) 抽锚点(样例:AS400 用 IBM i 导出的 CSV,Java 用 AST 解析器的产物)
python tools/ingest_ibmi_metadata.py --dsppgmref samples/ibmi_exports/dsppgmref.csv --dspffd samples/ibmi_exports/dspffd.csv --src samples/as400 --out analysis/anchors.as400.json
python tools/ingest_java_anchors.py  --in samples/java_extract/java-anchors.raw.json --out analysis/anchors.java.json

# 2) 切单元 + 分配给成员
python tools/build_units.py  --anchors analysis/anchors.as400.json analysis/anchors.java.json --out analysis/units.csv
python tools/assign_work.py  --units analysis/units.csv --names alice,bob,carol --out analysis/assignments

# 3) 成员产物已随样例附带(analysis/semantics、mapping、diffs…)。校验 + 验AI + 建地图 + 汇总:
python tools/validate_outputs.py  --path analysis
python tools/verify_semantics.py  --semantics analysis/semantics --anchors analysis/anchors.as400.json analysis/anchors.java.json --out analysis/qa
python tools/build_index.py       --semantics analysis/semantics --out analysis
python tools/import_runtime_diffs.py --in samples/runtime_dumps --out analysis/runtime_diffs.json
python tools/aggregate_matrix.py  --analysis analysis --out analysis/parity_matrix.json
```
最后一条会打印对等性矩阵:单侧桶计数、每类缺陷"风险点 N / 已验 M"、以及⚠"语义说相同但运行时说不同"的对。看到这些就说明链路通了。

---

## 2. 真实项目:怎么拿到**准确的**锚点(免费,不用商业工具)

锚点(表/字段/程序/调用/SQL 表)是整套方法的地基。**最准的锚点不靠解析源码,靠平台和编译器自带的元数据。** 两侧分别做:

### 2a. AS400 侧 —— 用 IBM i 自带的交叉引用命令
在 IBM i 上(5250 绿屏或 ACS 里)对你的库跑这两条,把结果导成输出文件:
```text
DSPPGMREF PGM(YOURLIB/*ALL) OUTPUT(*OUTFILE) OUTFILE(YOURLIB/PGMREF)
DSPFFD    FILE(YOURLIB/*ALL) OUTPUT(*OUTFILE) OUTFILE(YOURLIB/FFD)
```
把输出文件转成 CSV(`CPYTOIMPF`,或对 outfile 跑 SQL 再下载),列名映射成:
- `PGMREF` → 列 `program, referenced_object, object_type`(源字段 `WHPNAM / WHFNAM / WHOBJT`)
- `FFD`    → 列 `file, field`(源字段 `WHFILE / WHFLDE`)

把两个 CSV 拷到本机,然后归一成标准锚点:
```bash
python tools/ingest_ibmi_metadata.py --dsppgmref pgmref.csv --dspffd ffd.csv --src <AS400源码目录> --out analysis/anchors.as400.json
```
> `--src` 让脚本用程序名找回真实源码路径(后续按 path 对齐、验AI 都要它)。
> 还想更全:DB2 编目 `QSYS2.SYSCOLUMNS`(`--db2cols`)、编译器 `OPTION(*XREF)` 的交叉引用清单都能转成同样 CSV 喂进来。

### 2b. Java 侧 —— 用真正的 AST 解析器(JavaParser + JSqlParser)
**别用正则。** 仓库里 `java-extractor/` 是个 Maven 项目,用 JavaParser 出 AST(类/方法/调用图)、JSqlParser 解析 SQL 字符串、读 `@Table/@Column` 注解。构建并运行:
```bash
cd java-extractor
mvn -q clean package                                                   # 产出 target/java-anchor-extractor.jar
java -jar target/java-anchor-extractor.jar  <你的Java源码根目录>  out/java-anchors.raw.json
cd ..
python tools/ingest_java_anchors.py --in java-extractor/out/java-anchors.raw.json --out analysis/anchors.java.json
```
> 没装 JDK/Maven 时,可先用 `samples/java_extract/java-anchors.raw.json` 这份样例中间产物跑通 Python 侧。
> 细节(中间 JSON 字段契约、可扩展 MyBatis/端点)见 [java-extractor/README.md](java-extractor/README.md)。

### 2c. 兜底(没有上面任一来源时)
`extract_anchors.py` 是**正则启发式**,对 RPG 不完整、抽不准字段——只用于临时启动:
```bash
python tools/extract_anchors.py --src <源码目录> --side as400 --out analysis/anchors.as400.json
```
> 锚点抽取是**可插拔**的:任何来源只要产出标准 `anchors.<side>.json` 就能接下一步。所以你换任何工具都不影响后面。

拿到两侧锚点后,回到 **第 1 节的第 2)、3) 步**(切单元 → 分配 → 成员干 → 校验/汇总)。

---

## 3. 成员怎么干(Copilot Agent 模式)

**纪律:一个单元开一个全新 Chat,做完即关,绝不跨单元串上下文**——这是"独立运行"的唯一办法。
1. 打开 `analysis/assignments/<你的名字>.csv`,找下一个产物还不存在的单元。
2. 新建 Chat(选 `parity-analyzer` agent),打开该单元源文件。
3. 输入当前阶段的 `/` 命令(见下),agent 产出 JSON 到约定路径。
4. 自检:`python tools/validate_outputs.py --file <产物> --schema <名>`,不过就让 agent 改到过。
5. 关掉 Chat,下一个单元再开新的。

五步流水线(每步一个 skill + 一个 `/` 入口):
```
/extract-semantics → /align-mapping → /compare-pair → /generate-difftests → /propagate-pattern
   抽语义              锚点对齐分桶     规则级 diff      运行时测试规格         根因横扫 N/M
```

---

## 4. 分阶段:先 Java 后 AS400(你的工作方式)

这套流水线天然支持分侧、分阶段,每阶段都有**独立可用**的产物:
1. **Java 阶段**:2b 抽 Java 锚点 → 全员 `/extract-semantics` 抽 Java 语义 → `verify_semantics`(只喂 java 锚点)验 AI → `build_index` 出 **Java 代码地图**。此时还没碰 AS400,产物已能用。
2. **AS400 阶段**:2a 抽 AS400 锚点 → 抽 AS400 语义 → 验 AI → 出 AS400 地图。
3. **对齐阶段**:两侧就绪后 `/align-mapping` → `/compare-pair` → `/generate-difftests` → `aggregate_matrix`。

---

## 5. 两个让结果可信的工具

- **用锚点验证 AI**(`verify_semantics.py`):LLM 语义会幻觉,但"引用了哪些表/调了谁"能确定性查。拿权威锚点当裁判:LLM 写了、权威里没有的 → `suspect`(疑似编的,非零退出可卡 CI);权威有、LLM 漏了 → `review`。
- **代码地图**(`build_index.py`):把锚点反转成 `by_table / by_field / by_call / call_graph`,产出 `analysis/index.<side>.json`。用法:**先查索引 JSON 定位单元,需要确切逻辑时再顺着 `units[].path` 打开源码**——即"先递推索引、再下钻代码"。

---

## 目录结构
```
.github/   copilot-instructions.md(方法论+纪律)、skills/(5)、prompts/(5)、agents/(parity-analyzer)
tools/     全部 Python:锚点抽取与适配、切单元/分配、校验、验AI、建索引、汇总
java-extractor/  Maven 项目:JavaParser + JSqlParser 抽 Java 锚点
schemas/   7 个 JSON schema(产物合同;不过 schema 不计 done)
docs/      METHODOLOGY / GLOSSARY / DEFECT-CLASSES / RUNBOOK / ANCHORS
analysis/  全部产物(semantics / mapping / diffs / tests / qa / index / assignments / 矩阵)
samples/   最小样例:RPG/Java 配对 + IBM i 导出 CSV + Java AST 中间产物 + units/assignments
```

## 边界
- `agent` 只写 `analysis/`,不碰源码/schema/tools。
- 非 UTF-8(EBCDIC/codepage)源文件,工具会**告警跳过**不崩;需转码或换来源。
- 商业工具(Fresche X-Analysis / ARCAD / IBM ADDI)是**可选**替代,本仓库的免费路径(IBM i 命令 + JavaParser)已够用,不依赖它们。
- 本脚手架不假装做真实代码分析;`samples/` 仅为端到端演示。

## 延伸
- 锚点准确度阶梯 + 验AI + 分阶段:[docs/ANCHORS.md](docs/ANCHORS.md)
- 协调人/成员逐步操作手册:[docs/RUNBOOK.md](docs/RUNBOOK.md)
- 方法论十条:[docs/METHODOLOGY.md](docs/METHODOLOGY.md);缺陷类清单:[docs/DEFECT-CLASSES.md](docs/DEFECT-CLASSES.md)
- 样例端到端走查:[samples/README.md](samples/README.md)
