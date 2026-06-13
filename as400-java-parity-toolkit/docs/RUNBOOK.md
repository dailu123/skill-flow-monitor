# RUNBOOK — 操作手册(协调人 + 10 名成员)

面向两类角色:**协调人**(跑离线 Python、建题、分配、汇总、合并)和**成员**(在 Copilot agent 里逐单元干活)。
环境:Windows + VS Code + GitHub Copilot **Agent 模式**。**没有 Copilot CLI**。

> 前置确认:请团队在 README 里确认本机 VS Code 版本支持 `.github/skills/**/SKILL.md`(Copilot agent 模式自 **2026-04** 起支持)。**若版本暂不支持 SKILL.md,退一步用 `/<step>` prompt 文件入口照样能跑**,skill 只是把方法整理得更顺、能渐进加载参考资料。

---

## 一、协调人:一次性环境准备
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r tools\requirements.txt
```
> 路径含空格/中文也没问题(脚本统一用 pathlib)。读 AS400 源码时遇到非 UTF-8(疑似 EBCDIC/codepage)文件会**告警跳过**,不崩。

## 二、协调人:建题与分配(离线 Python)
1. **抽锚点** —— 推荐用**免费的权威来源**(完整说明见 [ANCHORS.md](ANCHORS.md)),不必用商业工具:
   ```bat
   :: AS400: IBM i 平台交叉引用(DSPPGMREF/DSPFFD)导出 CSV 后归一
   python tools\ingest_ibmi_metadata.py --dsppgmref pgmref.csv --dspffd ffd.csv --src <源码目录> --out analysis\anchors.as400.json
   :: Java: 先用 java-extractor(JavaParser+JSqlParser)产中间 JSON,再归一
   python tools\ingest_java_anchors.py --in java-extractor\out\java-anchors.raw.json --out analysis\anchors.java.json
   ```
   > 兜底:实在没有上述来源时,`extract_anchors.py`(正则,best-effort,对 RPG 不完整)可临时启动。
   > 锚点抽取是可插拔的:任何来源产出标准 `anchors.<side>.json` 都能喂下一步。
2. **切单元**:
   ```bat
   python tools\build_units.py --anchors analysis\anchors.as400.json analysis\anchors.java.json --out analysis\units.csv
   ```
3. **分配给 10 人**(均衡 token、分散高风险):
   ```bat
   python tools\assign_work.py --units analysis\units.csv --names 张三,李四,王五,... --out analysis\assignments
   ```
   生成 `analysis/assignments/<名字>.csv`,每行一个单元,含 `artifact` 约定产出路径。
4. 提交并通知成员拉取。

## 三、成员:在 Copilot Agent 模式逐单元干活
**核心纪律:每个单元开一个全新 Chat,做完即关,绝不跨单元带上下文。**
1. 打开自己的 `analysis/assignments/<名字>.csv`,找下一个 `status != done`(或产物文件还不存在)的单元。
2. **新建一个 Chat 会话**,选 `parity-analyzer` agent(或默认 agent + copilot-instructions)。
3. 打开该单元的源文件,在 Chat 里输入对应 `/` 命令:
   - 语义抽取:`/extract-semantics`
   - 对齐:`/align-mapping`
   - 精细对比:`/compare-pair`
   - 差异测试规格:`/generate-difftests`
   - 根因传播:`/propagate-pattern`
   > 若你的 VS Code 支持 SKILL.md,描述匹配时 skill 也会自动协助;`/` 入口保证**可预测、显式触发**。
4. agent 产出 JSON 到 `artifact` 路径后,**自检**:
   ```bat
   python tools\validate_outputs.py --file analysis\semantics\<unit_id>.json --schema semantics
   ```
   不过就让 agent 改到过。
5. **关掉这个 Chat**,下一个单元再开新的。

## 四、成员:提交
- 每人一个分支(或自己的子目录),只改 `analysis/` 下自己的产物。
- 提交前自检全过:`python tools\validate_outputs.py --path analysis\semantics`。

## 五、协调人:合并与汇总
1. 合并各分支(产物互不重叠,冲突极少)。
2. **批量校验**(不过的不计入 done):
   ```bat
   python tools\validate_outputs.py --path analysis
   ```
3. **用锚点验证 AI**(抓 LLM 幻觉/漏抽,`suspect` 非零退出可卡 CI):
   ```bat
   python tools\verify_semantics.py --semantics analysis\semantics --anchors analysis\anchors.as400.json analysis\anchors.java.json --out analysis\qa
   ```
4. **生成代码地图**(表→单元反向索引,支持"先索引后下钻源码"):
   ```bat
   python tools\build_index.py --semantics analysis\semantics --out analysis
   ```
5. **刷新进度看板**(按产物存在性+schema 自动判,勿手改 status):
   ```bat
   python tools\progress.py --assignments analysis\assignments --out analysis\PROGRESS.md
   ```
6. (可选)**导入运行时 diff**:
   ```bat
   python tools\import_runtime_diffs.py --in runtime_dumps --out analysis\runtime_diffs.json
   ```
7. **汇总对等性矩阵**:
   ```bat
   python tools\aggregate_matrix.py --analysis analysis --out analysis\parity_matrix.json
   ```
   stdout 会打印:单侧桶计数、每缺陷类"分类风险点 N / 已验 M"、以及⚠"语义说相同/运行时说不同"的对。

## 六、阶段推进(支持先 Java 后 AS400)
- **Java 阶段**:`ingest_java_anchors` → 全员 `/extract-semantics` 抽 Java → `verify_semantics`(只喂 java 锚点)→ `build_index` 出 Java 代码地图。这一阶段产物独立可用。
- **AS400 阶段**:`ingest_ibmi_metadata` → 抽 AS400 语义 → verify → 出 AS400 地图。
- **对齐阶段**:两侧就绪后 `/align-mapping` → 对 `matched` 跑 `/compare-pair` → 对存疑规则 `/generate-difftests` → 对确凿差异 `/propagate-pattern`。
- 每轮结束跑 `verify_semantics.py` + `progress.py` + `aggregate_matrix.py` 看质量与残差收敛。

## 常见问题
- **非 UTF-8 源文件被跳过**:正常,EBCDIC/codepage 文件需专业工具转码或导出锚点;别强行解码。
- **schema 不过算没做完**:`progress.py` 把 schema 不过的产物标 `invalid`,不计 done。
- **状态打架**:不要手改 CSV 的 status;一律以"产物文件存在 + schema 通过"为准。
