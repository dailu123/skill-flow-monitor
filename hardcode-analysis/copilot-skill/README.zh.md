# 用 Copilot 找硬编码 —— 分享给同事/领导的 Skill

> English: [README.md](./README.md)

这是一个 **GitHub Copilot Skill**(`.github/skills/` 文件夹格式)。把一个文件夹放进仓库,就能在
Copilot Chat 里用一句话扫出代码里**写死的业务值/代码**(branch/status/group member 等)。
**什么都不改也能用**(尽量多地找);也可以改顶部配置做定制。

> ⚠️ 这是**尽力而为的辅助**,结果是给人复核的候选,不保证 100%。要"可复现、保证不漏"的全量扫描,
> 用随附的确定性 Python 工具(见上级目录 `hardcode-analysis/`)。本 skill 是好分享的轻量版。

## 它怎么干活(三步)
1. **先把候选捞全**(机械搜索,任何编码):凡是 group member 字段被赋值/比较、或用户给的目标值
   出现的地方(含 `X'..'` 十六进制)——全列出来,先不判断。
2. **AI 逐个判断**每一处是不是 hardcode,给结论 + 理由(按内置规则)。
3. **给出完整 list**(确认的命中表 + 汇总)。

---

## 一、怎么用(两种,任选)

**方式 A:作为 Skill(推荐,可重复用 `/` 调用)**
1. 把整个 [`find-hardcodes/`](./find-hardcodes/) 文件夹复制到你仓库的 **`.github/skills/`** 下
   (即 `.github/skills/find-hardcodes/SKILL.md`)。
2. 在 Copilot Chat(Agent 模式)里打 `/find-hardcodes`,回车;可再补一句范围,如"扫 sources/CHN_HUB_IB"。
   Agent 启动时会自动发现并加载这个 skill。

**方式 B:最省事(不用任何配置)**
1. 打开 Copilot Chat。
2. 把 `find-hardcodes/SKILL.md` 的**全部内容粘贴**进去。
3. 末尾加一句:"按上面三步扫 `<你的文件夹>`,输出表格。"

> **要不要 `copilot-instructions.md`?不需要。** 那个文件是**每次对话都自动注入**的全局指令,
> 不适合"找硬编码"这种按需任务。Skill 是按需 `/` 调用,正好。

---

## 二、怎么定制(改顶部 CONFIG 块就行)

配置块在 prompt 文件最上面。**留空或写 `ANY` = 用最宽的默认**。常见改法:

| 你想做的 | 改哪行 | 例子 |
|---|---|---|
| 只找某几个固定值 | `TARGET_VALUES` | `TARGET_VALUES = HAAA,HBBJ,HBCB,HSBC` |
| 值的形状提示 | `VALUE_SHAPE` | `VALUE_SHAPE = 4 个字母、以 H 开头` |
| 值贴在哪个字段(前缀匹配) | `FIELD_PATTERNS` | `FIELD_PATTERNS = ??GMAB`(`?`=任一字符,`*`=多个) |
| 只扫某些路径 | `INCLUDE_GLOBS` | `INCLUDE_GLOBS = sources/**, src/**` |
| 不扫某些路径 | `EXCLUDE_GLOBS` | `EXCLUDE_GLOBS = **/test/**, **/generated/**` |
| 不扫某些后缀 | `EXCLUDE_EXTS` | `EXCLUDE_EXTS = .md,.json,.log,.txt` |
| 只扫文件/文件夹名以某串开头的 | `NAME_STARTS_WITH` | `NAME_STARTS_WITH = IB,GL` |
| 主机字符集(影响 hex) | `EBCDIC_CCSID` | `EBCDIC_CCSID = 937` |
| 自己加排除规则(自然语言) | `EXTRA_EXCLUDE` | 见下 |

`EXTRA_EXCLUDE` 用自然语言一行一条,Copilot 会照办,例如:
```
EXTRA_EXCLUDE =
  忽略 %EDITC 编辑码里的单字符（'X' 'Y'）
  忽略拼接消息文本里的分隔符
  忽略 W3SFRC 这个字段相关的命中
```

---

## 三、它会找什么 / 不找什么(已内置规则)

**算硬编码**:字段与固定值是同一个**比较/赋值/常量定义**的两端 ——
`IF L1GMAB='HBCB'`、`MOVE 'HSBC' K7GMAB`、`dcl-c W0gmab const('HSBC')`、
`%SUBST(L1GMAB:1:2)='HB'`、十六进制 `X'C8C2C3C2'`。

**不算(自动排除)**:注释、字段名/变量名、字段对字段(`MOVE A B`)、拼接分隔符
(`+ ' ' +`)、复合条件里属于别的字段的值、满天飞的公司/库名,以及你在 `EXTRA_EXCLUDE` 里加的。

输出一张表:文件、行号、值、形式(文本/hex)、类型、字段、置信度(HIGH/MEDIUM/LOW)、命中那一行。

---

## 四、给别人讲的一句话

> "把 `find-hardcodes/` 文件夹放进 `.github/skills/`,在 Copilot Chat 打 `/find-hardcodes` 就能扫硬编码:
> **先把候选捞全 → AI 逐个判断 → 出完整 list**;改 SKILL.md 最上面的配置块能指定扫哪些、不扫哪些、
> 找什么值、加排除规则。结果要人复核。"
