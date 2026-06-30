# GMAB 硬编码扫描 —— 独立 Copilot Skill

> English: [README.md](./README.md)

一个**自洽、可分享的 GitHub Copilot Skill**:放进仓库,在 Copilot Chat 里一句话就能扫出代码里
**写死的 group member / 业务值**(AS/400 RPG/CL/COBOL 或一般代码)。SKILL.md **不塞死代码**,而是
用**精确的自然语言规格**让 AI **自己生成并运行**一个搜索脚本(默认 **PowerShell**、零安装;原始
EBCDIC 文件就让 AI 改用 **Python**)。规格里每个细节都钉好了,人类也能直接改。

> ⚠️ 尽力而为的辅助,结果是**给人复核的候选**,不保证 100%。

## 怎么干活(三步,写在 SKILL.md 里)
1. **捞全候选**:skill 用自然语言把规则讲死(扫哪些文件、怎么判注释、怎么认字段、要带引号、怎么解
   EBCDIC、hex 映射、输出列),**让 AI 据此自己写一个搜索脚本并运行**,把候选行全导出 `candidates.csv`。
   默认 PowerShell(零安装),EBCDIC 就切 Python。**能扛几千万行**,先不判断、宁多勿漏。
2. **逐个判断**:AI 读 `candidates.csv`,对每一行判 **是/否 hardcode + 理由 + 置信度**(按内置规则:
   比较/赋值/const 绑定算;字段间、拼接分隔符、复合条件里别的字段的值、注释 不算)。
3. **出完整 list**:确认命中的表格 + 汇总。

---

## 一、怎么用(两种)

**方式 A:作为 Skill(推荐)**
1. 把整个 [`find-hardcodes/`](./find-hardcodes/) 文件夹(里面就一个 `SKILL.md`)复制到目标仓库的
   **`.github/skills/`** 下。
2. Copilot Chat(Agent 模式)里打 `/find-hardcodes`,补一句范围,如"扫 sources/CHN_HUB_IB"。
   AI 会按三步:**按规格生成搜索脚本并运行**捞候选 → 逐个判断 → 出表。

**方式 B:不装,直接粘贴**
1. 打开 Copilot Chat,把 `find-hardcodes/SKILL.md` 全文粘进去。
2. 加一句:"按上面三步,先按 STEP 1 的规格生成并运行搜索脚本扫 `<我的文件夹>`,再判断、出表。"

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
| 自加排除规则(自然语言) | `EXTRA_EXCLUDE` | 一行一条,STEP 2 时照办 |

改了 CONFIG,AI 生成脚本时会照着来。你也可以**直接改 SKILL.md 里 STEP 1 的自然语言规则**(比如改
字段判定、改注释规则、加范围条件)——AI 就按你改后的规格生成脚本。整份规格是给人改的。

---

## 给别人讲的一句话

> "把 `find-hardcodes/` 放进 `.github/skills/`,Copilot Chat 打 `/find-hardcodes`:它**按规格自己
> 生成搜索脚本把候选捞全 → AI 逐个判断 → 出完整 list**;改 SKILL.md 顶部 CONFIG 选扫哪些/找什么/加排除。结果要人复核。"
