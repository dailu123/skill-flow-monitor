# GMAB Hardcode Scan — standalone Copilot Skill

> 中文：[README.zh.md](./README.zh.md)

A **self-contained, shareable GitHub Copilot Skill**: drop it into a repo and, from Copilot Chat,
find where **group member / business values are hardcoded** (AS/400 RPG/CL/COBOL or general code).
SKILL.md contains **no code** — it specifies, in **precise natural language**, exactly what to do,
and the AI **generates and runs the search script itself** (default **PowerShell**, no install;
**Python** when files are raw EBCDIC). Every detail is pinned down in the spec, and a human can
edit it. The skill does the whole job end to end.

> ⚠️ Best-effort assistance — results are **candidates for human review**, not a guarantee.

## How it works (three steps, defined in SKILL.md)
1. **Gather all candidates:** following a precise spec (which files, comment rule, field rule,
   require a quote, EBCDIC decoding, hex mapping, output columns), the AI **writes and runs a
   search script** that exports every candidate line to `candidates.csv`. Default PowerShell
   (no install); Python for raw EBCDIC. Scales to tens of millions of lines.
2. **Judge each candidate:** the AI reads `candidates.csv` and rules each one YES/NO + reason +
   confidence (compare/assign/const bind → yes; field-to-field, concat separators, a different
   field's value in a compound test, comments → no).
3. **Final list:** confirmed hits table + summary.

---

## 1. How to use (two ways)

**Option A — as a Skill (recommended)**
1. Copy the whole [`find-hardcodes/`](./find-hardcodes/) folder (just `SKILL.md`) into the target
   repo's **`.github/skills/`**.
2. In Copilot Chat (Agent mode) type `/find-hardcodes` and add a scope, e.g. "scan
   sources/CHN_HUB_IB". The AI generates & runs the search script → judges → outputs the table.

**Option B — no install, just paste**
1. Paste the full `find-hardcodes/SKILL.md` into Copilot Chat.
2. Add: "Following the three steps, generate and run the STEP 1 search script on `<folder>`, then
   judge and output the table."

> **Need `copilot-instructions.md`? No** — that is injected into every chat; wrong for an
> on-demand task. A Skill is invoked on demand with `/`.

---

## 2. Customise (edit the CONFIG block at the top of SKILL.md)

| Goal | Field | Example |
|------|-------|---------|
| Only a fixed set of values | `TARGET_VALUES` | `HAAA,HBBJ,HBCB,HSBC` |
| Field name(s), prefix match (incl. bare GMAB) | `FIELD_PATTERNS` | `GMAB,??GMAB` (`?`=one char, `*`=many) |
| Only / never scan some paths | `INCLUDE_GLOBS` / `EXCLUDE_GLOBS` | `sources/**` / `**/test/**` |
| Skip some extensions | `EXCLUDE_EXTS` | `.md,.json,.log` |
| Only files/folders whose name starts with… | `NAME_STARTS_WITH` | `IB,GL` |
| Your own exclusions (plain language) | `EXTRA_EXCLUDE` | one rule per line, applied in STEP 2 |

After editing CONFIG, the AI generates the script accordingly. You can also **edit the STEP 1
natural-language rules** in SKILL.md directly (e.g. change the field rule, the comment rule, add a
scope condition) — the AI will follow your edited spec. The whole spec is meant to be edited.

---

## One-liner to pass on

> "Drop `find-hardcodes/` into `.github/skills/`, type `/find-hardcodes` in Copilot Chat: it
> **generates a search script from the spec to gather all candidates → judges each → outputs the
> final list**; edit the CONFIG block in SKILL.md to choose what to scan, which values, and
> exclusions. Review results."
