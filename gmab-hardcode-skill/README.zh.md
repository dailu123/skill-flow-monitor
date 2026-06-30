# GMAB 硬编码扫描 —— 独立 Copilot Skill

> English: [README.md](./README.md)

一个**自洽、可分享的 GitHub Copilot Skill**:放进仓库,在 Copilot Chat 里一句话就能扫出代码里
**写死的 group member / 业务值**(AS/400 RPG/CL/COBOL 或一般代码)。**不依赖任何外部工具**,
skill 本身从头到尾把活干完。

> ⚠️ 尽力而为的辅助,结果是**给人复核的候选**,不保证 100%。

## 怎么干活(三步,写在 SKILL.md 里)
1. **捞全候选**:skill 让 AI 写下并运行一个**零依赖小脚本** `gather_candidates.py`——它确定性地
   遍历源码、跳过注释、识别任何编码(UTF-8/EBCDIC)、把"字段+字面量 / 目标值 / `X'..'` 十六进制"
   的行全导出到 `candidates.csv`。**这一步靠脚本,能扛几千万行**,先不判断、宁多勿漏。
2. **逐个判断**:AI 读 `candidates.csv`,对每一行判 **是/否 hardcode + 理由 + 置信度**(按内置规则:
   比较/赋值/const 绑定算;字段间、拼接分隔符、复合条件里别的字段的值、注释 不算)。
3. **出完整 list**:确认命中的表格 + 汇总。

---

## 一、怎么用(两种)

**方式 A:作为 Skill(推荐)**
1. 把整个 [`find-hardcodes/`](./find-hardcodes/) 文件夹(含 `SKILL.md` 和 `gather_candidates.py`)
   复制到目标仓库的 **`.github/skills/`** 下。
2. Copilot Chat(Agent 模式)里打 `/find-hardcodes`,补一句范围,如"扫 sources/CHN_HUB_IB"。
   AI 会按三步:跑脚本捞候选 → 逐个判断 → 出表。

**方式 B:不装,直接粘贴**
1. 打开 Copilot Chat,把 `find-hardcodes/SKILL.md` 全文粘进去。
2. 加一句:"按上面三步,先创建并运行 gather_candidates.py 扫 `<我的文件夹>`,再判断、出表。"
   (SKILL.md 里内嵌了脚本全文,AI 会照着创建文件。)

> **要不要 `copilot-instructions.md`?不需要**——那是每次对话自动注入的全局指令,不适合按需任务。
> Skill 是 `/` 按需调用,正合适。

---

## 二、怎么定制(改 SKILL.md 顶部 CONFIG)

| 想做 | 改哪行 | 例子 |
|---|---|---|
| 只找某几个值 | `TARGET_VALUES` | `HAAA,HBBJ,HBCB,HSBC` |
| 字段名(前缀匹配,含裸 GMAB) | `FIELD_PATTERNS` | `GMAB,??GMAB`(`?`=任一字符,`*`=多个) |
| 只扫/不扫某些路径 | `INCLUDE_GLOBS` / `EXCLUDE_GLOBS` | `sources/**` / `**/test/**` |
| 不扫某些后缀 | `EXCLUDE_EXTS` | `.md,.json,.log` |
| 只扫名字以某串开头的文件/文件夹 | `NAME_STARTS_WITH` | `IB,GL` |
| 主机字符集(影响 hex) | `EBCDIC_CCSID` | `937`(对纯字母值与 cp037 等价) |
| 自加排除规则(自然语言) | `EXTRA_EXCLUDE` | 一行一条,STEP 2 时照办 |

脚本同样接受对应的 `--flag`(`--fields --targets --include --exclude --exclude-exts
--name-starts --ccsid`),改 CONFIG 后按提示传进去即可。

---

## 给别人讲的一句话

> "把 `find-hardcodes/` 放进 `.github/skills/`,Copilot Chat 打 `/find-hardcodes`:它**先跑个小脚本
> 把候选捞全 → AI 逐个判断 → 出完整 list**;改 SKILL.md 顶部 CONFIG 选扫哪些/找什么/加排除。结果要人复核。"
