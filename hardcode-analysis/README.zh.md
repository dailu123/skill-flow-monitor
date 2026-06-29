# 硬编码分析 — GMAB 匹配器

> English version: [README.md](./README.md)

在大型 IBM i(AS/400)银行代码库里**确定性**定位 15 个 group member(GMAB)值被**硬编码**的位置，
产出可复现的结构化清单，供 Java 重写 parity 验证。

**两种用法:**
- **确定性 Python 工具**(本文档)——可复现、不漏、离线跑。兜底基线。
- **Copilot Chat skill**([`copilot-skill/`](./copilot-skill/))——一个可分享的 prompt file,
  教 Copilot 做同样的事,尽力而为、可配置。适合只有 Copilot Chat、想方便分享给别人的场景。

**纯 Python 标准库，Windows 可跑，召回全靠规则——召回路径里不调用 LLM。** LLM 仅可作可选步骤：
(a) 事后对 MEDIUM 条目分类；(b) 编写新的检测模式(见 skill)。它绝不逐行阅读源码去"找"硬编码。

## 为什么用规则而非逐行 AI 阅读

这是确定性提取任务，不是判断任务。逐行 AI 阅读不可复现、有漏读风险、成本随代码量线性增长。
召回必须靠规则保证 100%，LLM 充其量只在最后做可选标注。

## 模块（数据流）

1. `literal_extractor.py` — **约束 1**：按文件嗅探编码(先 UTF-8 严格，再 EBCDIC/latin-1)，
   再用一套容错词法切出**字符串字面量**(单/双引号、`''` 转义、注释剔除、`X'..'` hex、续行)。
   不在原始行 grep，不按文件名派发词法。
2. `value_matcher.py` — **约束 2/3**：锚点 A。15 值精确匹配(区分大小写、完整 4 位)+ EBCDIC
   hex 形式(`build_hex_table`，cp037)。
3. `field_matcher.py` — **约束 4/5/6**：逻辑语句分段(EXEC SQL 块到 `;`、free 续行、定长按行)，
   判定字面量是否**贴 group member 字段**(token 边界，避免 `GRPMBR_FLAG` 误命中)。
4. `patterns.py` — **可扩展性**：从 JSON(`--patterns`)加载额外的用户检测模式的引擎。两个核心
   锚点保持硬编码；模式在不改代码的前提下增加召回(路由 helper 调用、另一种编码、新的前缀比较
   写法)。LLM 只负责写正则，匹配仍是确定性的。
5. `merge_dedup.py` — **约束 7**：A ∪ B ∪ patterns 取并集，按 `program+member+行+列+值` 去重。
   HSBC 仅贴字段才保留。HIGH=贴字段 / MEDIUM=未贴字段。
6. `report.py` — 产出 `gmab_hits.csv` 与 `gmab_summary.md`(每值计数、ASCII/HEX、HIGH/MEDIUM、
   list 外候选异常值)。

## 跑之前必做

1. **前置验证**：在 IBM i 上跑 `hardcode_matcher/precheck.sql`，确认 15 值是否就是真实数据全集，
   并查出 group member **真实列名/别名**。
2. 回填 `hardcode_matcher/config.py`：`FIELD_NAMES`(真实列名，可多个)、必要时 `EBCDIC_CODEC`。
   `GMAB_VALUES` 是**封闭枚举**——出现第 16 个值须人确认后才并入，工具不擅自改。

## 运行（Windows）

```
python -m hardcode_matcher.run --src <HUB源码根目录> --out gmab_out \
    --fields "??GMAB" --ccsid cp037 \
    --patterns patterns/custom_patterns.example.json
```

参数含义：

- `--src` — 要扫的源码根目录（递归、全文件、不按文件名派发）。指向**纯 HUB 源码**（勿混入本
  工具或其它语言文件，否则会扫出无关字面量）。
- `--out` — 输出目录，生成 `gmab_hits.csv` + `gmab_summary.md`。
- `--fields` — group member **列名**（逗号分隔），用于锚点 B（贴字段判定）。支持通配符：
  `?`=一个标识符字符，`*`=多个。HUB 里该列有**两位可变前缀**，故用 `"??GMAB"`（能匹配
  `01GMAB`、`bkGMAB` 等，但不匹配裸 `GMAB`、三位前缀、或 `xxGMAB_FLAG`）。
- `--ccsid` — EBCDIC codec（默认 `cp037`=CCSID 037）。两个用途：解码原始 EBCDIC 源码、
  生成每个值的 EBCDIC 字节以匹配 `X'..'` hex 形式。主机 CCSID 不同则改（如 1388，见已知边界）。
- `--exts` — 可选扩展名过滤；默认全扫。
- `--patterns` — 可选自定义模式 JSON；省略则只用锚点 A/B。
- `--progress-secs` — 进度打印间隔(默认 2.0；`0` 关闭)。进度打到 stderr：先枚举文件，再每隔
  几秒打 `[百分比] files i/N lines 行数 hits 命中 f/s elapsed ETA | 当前文件`，跑几千万行时
  能看到在动、卡在哪个文件。

## 输出列

`program, member, line, col, matched_value, match_form(ASCII/HEX), anchor(A/B),
statement(±2 行上下文), field_adjacent, confidence(HIGH/MEDIUM), lang, pattern`

## 用新模式扩展

当你（或同事）凭经验发现另一种硬编码写法时，**不改代码**，往一个 JSON 文件里加一条模式即可。
每条模式 = 一个正则(带命名组 `value`) + 元数据。见 `patterns/custom_patterns.example.json`
与 skill [`../SKILL_hardcode-analysis.md`](../SKILL_hardcode-analysis.md)——它指导 LLM 写出一条
经校验的模式条目（且未经确认绝不扩大 GMAB 值集合）。

## 自检

```
python -m hardcode_matcher.samples.selftest
```

已验证：定长 RPG 列号、`''` 转义不提前断串、注释(第 7 列 `*`、`//`、`*>`、`--`、`/* */`)剔除、
EBCDIC 文件解码、`X'C8C2C3C2'`→HBCB hex 命中、`%SUBST(GRPMBR:1:2)='HB'` 前缀入锚点 B、
HSBC 贴字段保留/不贴丢弃、`GRPMBR_FLAG` 不算字段、以及自定义模式引擎。

## 真实 IBM i 源码注意事项

- **SEU 行号/日期/变更号前缀(宽度可变)**：member 每行带数字前缀(`000400250811     C ...`，
  或 5 位变更号如 `10491H*`)，会把定长列整体右移。注释判定**不依赖固定列宽**:凡是
  「行首数字/空格 + RPG 规格字母 + `*` 或 `/`」即为注释——不管前缀多少位、甚至不同 member
  宽度不同都能对。否则注释里的撇号(如 `Customer's DCN`)会开跨行字符串、吞掉真实值。
- **子句级绑定(精度)**：锚点 B 只在字面量与 GMAB 字段处于**同一个 `AND`/`OR` 比较子句**
  时才判为硬编码——所以 `IF (L1STUS='1') AND (L1GMAB<>W3GMAB)` 和字段间比较**不会**误报,
  而 `IF L1GMAB='HBCB'`、`MOVE 'HSBC' K7GMAB`、`%SUBST(L1GMAB:1:2)='HB'` 会保留。
- 引号字面量在行尾即闭合(不跨物理行),从而限制任何畸形/未闭合串的影响范围。

## 已知边界（写匹配器前已声明的假设）

- CCSID 1388(主机 GBK) Python 无内置 codec，需另配映射；默认 037。
- 字面量提取是**词法层**，非完整语法树；跨续行拼接 GMAB 值的极端情况靠「行尾未闭合串自动拼接」兜底。
- LLM 仅作可选**后置**步骤(分类 MEDIUM / 写模式)，须 batch、只喂字面量切片，不喂整文件；召回不依赖它。
