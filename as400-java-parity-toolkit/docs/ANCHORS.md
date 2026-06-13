# ANCHORS — 不用商业工具,如何拿到精确锚点 + 用锚点验证 AI

锚点是整套方法的地基(见 METHODOLOGY 第 1 条)。**锚点越准,对齐越准,AI 幻觉越好抓。**
本文讲:不依赖 Fresche/ARCAD/ADDI,如何免费拿到准确锚点,以及怎么用锚点反过来验 AI。

核心设计:**锚点抽取是可插拔的**。任何来源只要产出标准 `anchors.<side>.json`
(格式见 `tools/extract_anchors.py` / 适配器输出),都能喂 `build_units.py`。
`extract_anchors.py`(正则)是**最弱兜底**,生产请换成下面的权威来源。

## 准确度阶梯(从最准到兜底)

| 来源 | 侧 | 准确度 | 免费? | 工具 |
| --- | --- | --- | --- | --- |
| IBM i 平台交叉引用(DSPPGMREF/DSPFFD/DSPDBR) | AS400 | 权威 | ✅ | `tools/ingest_ibmi_metadata.py` |
| DB2 编目(QSYS2.SYSTABLES/SYSCOLUMNS) | AS400 | 权威 | ✅ | `ingest_ibmi_metadata.py --db2cols` |
| 编译器 *XREF(CRTBNDRPG/COBOL OPTION(\*XREF)) | AS400 | 权威 | ✅ | 转 CSV 后喂 `ingest_ibmi_metadata.py` |
| DDS 解析(PF/LF/DSPF 定宽) | AS400 | 高 | ✅ | 可自写解析器,转锚点格式 |
| JavaParser/Spoon + JSqlParser | Java | 接近 100% | ✅ | `java-extractor/` + `ingest_java_anchors.py` |
| 正则启发式 | 两侧 | 低/不完整 | ✅ | `extract_anchors.py`(兜底) |

### AS400:用平台自带命令(最准且免费)
不解析 RPG 源码,直接导出 IBM i 自己的交叉引用:
```
DSPPGMREF PGM(YOURLIB/*ALL) OUTPUT(*OUTFILE) OUTFILE(YOURLIB/PGMREF)
DSPFFD    FILE(YOURLIB/*ALL) OUTPUT(*OUTFILE) OUTFILE(YOURLIB/FFD)
```
把输出文件转 CSV(`CPYTOIMPF` 或对 outfile 跑 SQL),列名映射:
- DSPPGMREF:`WHPNAM→program`、`WHFNAM→referenced_object`、`WHOBJT→object_type`
- DSPFFD:`WHFILE→file`、`WHFLDE→field`

然后:
```bat
python tools\ingest_ibmi_metadata.py --dsppgmref pgmref.csv --dspffd ffd.csv --src <源码目录> --out analysis\anchors.as400.json
```
> `--src` 让脚本把程序名解析回真实源码路径,便于和语义产物按 path 对齐(verify 需要)。
> 编译器 `OPTION(*XREF)` 的交叉引用清单同样可转成这两个 CSV 喂进来。

### Java:用真正的 AST 解析器(接近 100% 准)
**别用正则**。`java-extractor/`(Maven 项目)用:
- **JavaParser** 出 AST → 类、方法、调用图;
- **JSqlParser** 解析代码里的 SQL 字符串 → 表/列;
- 读 `@Table/@Entity/@Column` → JPA 表/列;
- (可扩展)MyBatis mapper XML、`@RequestMapping`。

构建运行见 `java-extractor/README.md`。产出中间 JSON 后:
```bat
python tools\ingest_java_anchors.py --in java-extractor\out\java-anchors.raw.json --out analysis\anchors.java.json
```
> 没装 JDK/Maven 也能先跑通:`samples/java_extract/java-anchors.raw.json` 是中间 JSON 样例。

## 用锚点验证 AI(verify_semantics.py)

LLM 抽的语义会幻觉,但"这个单元引用了哪些表/调用了谁"能确定性查。
`verify_semantics.py` 拿确定性锚点当 oracle 给 LLM 产物判分:

- **幻觉 (hallucination)**:LLM 写了、权威来源里没有的表/调用 → `suspect`(疑似编的,非零退出可卡 CI)。
- **漏抽 (omission)**:权威来源有、LLM 没写 → `review`(召回不足/没忠实复制锚点)。
- **一致** → `ok`;**无确定性记录** → `unverifiable`。

```bat
python tools\verify_semantics.py --semantics analysis\semantics ^
    --anchors analysis\anchors.as400.json analysis\anchors.java.json --out analysis\qa
```
权威度自动判:来源是 `ibmi-outfile`/`java-parser`/`compiler-xref` → 失配是强信号;
是 `regex-best-effort` → 仅供参考。**表按 native∪sql 的并集比对**(因为 DSPPGMREF 区分不了访问方式,强分会假阳性)。

验证分层(从结构到运行时,层层加强):
1. `validate_outputs.py` — schema 结构。
2. `verify_semantics.py` — 锚点对账(查幻觉/漏抽)。← 本文重点
3. compare-pair 跨侧一致性 — 规则引用的字段两侧都该有。
4. `generate-difftests` + 运行时 diff — 最终 oracle。

## 代码地图:递推索引 → 下钻代码(build_index.py)

`build_index.py` 把语义产物的锚点反转成"代码地图":
```bat
python tools\build_index.py --semantics analysis\semantics --out analysis
:: 产出 analysis\index.as400.json 与 analysis\index.java.json
```
每份索引含 `by_table`(表→单元)、`by_field`、`by_call`、`call_graph`、`units`。
用法:**先查索引 JSON(便宜、结构化)定位到单元,需要确切逻辑时再顺着 `units[].path` 打开源码。**
这就是"先递推索引、到具体再看代码"的落地;每侧索引也是分阶段(先 Java 后 AS400)的独立产物。

## 分阶段工作流(先 Java 后 AS400)
这套流水线天然支持分侧分阶段:
1. **Java 阶段**:`java-extractor` → `ingest_java_anchors` → 全员 `/extract-semantics` 抽 Java →
   `verify_semantics`(只喂 java 锚点)对账 → `build_index` 出 Java 代码地图。**这一阶段的产物独立可用。**
2. **AS400 阶段**:`ingest_ibmi_metadata` → 抽 AS400 语义 → verify → 出 AS400 地图。
3. **对齐阶段**:两侧都就绪后 `/align-mapping` → `/compare-pair` → `/generate-difftests` → `aggregate_matrix`。
