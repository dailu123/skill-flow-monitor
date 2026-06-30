# GMAB Hardcode Scan — standalone Copilot Skill

> 中文：[README.zh.md](./README.zh.md)

A **self-contained, shareable GitHub Copilot Skill**: drop it into a repo and, from Copilot Chat,
find where **group member / business values are hardcoded** (AS/400 RPG/CL/COBOL or general code).
It depends on **nothing external** — the skill does the whole job end to end.

> ⚠️ Best-effort assistance — results are **candidates for human review**, not a guarantee.

## How it works (three steps, defined in SKILL.md)
1. **Gather all candidates:** the skill has the AI write & run a **dependency-free script**
   `gather_candidates.py`, which deterministically walks the source, skips comments, decodes any
   encoding (UTF-8/EBCDIC), and exports every line with `field + literal / target value / X'..'
   hex` to `candidates.csv`. **This step is a script, so it scales to tens of millions of lines.**
2. **Judge each candidate:** the AI reads `candidates.csv` and rules each one YES/NO + reason +
   confidence (compare/assign/const bind → yes; field-to-field, concat separators, a different
   field's value in a compound test, comments → no).
3. **Final list:** confirmed hits table + summary.

---

## 1. How to use (two ways)

**Option A — as a Skill (recommended)**
1. Copy the whole [`find-hardcodes/`](./find-hardcodes/) folder (with `SKILL.md` and
   `gather_candidates.py`) into the target repo's **`.github/skills/`**.
2. In Copilot Chat (Agent mode) type `/find-hardcodes` and add a scope, e.g. "scan
   sources/CHN_HUB_IB". The AI runs the script → judges → outputs the table.

**Option B — no install, just paste**
1. Paste the full `find-hardcodes/SKILL.md` into Copilot Chat.
2. Add: "Following the three steps, create and run gather_candidates.py on `<folder>`, then judge
   and output the table." (The script is embedded in SKILL.md, so the AI can recreate the file.)

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
| Host code page (affects hex) | `EBCDIC_CCSID` | `937` (== cp037 for letter values) |
| Your own exclusions (plain language) | `EXTRA_EXCLUDE` | one rule per line, applied in STEP 2 |

The script takes matching flags (`--fields --targets --include --exclude --exclude-exts
--name-starts --ccsid`); pass your CONFIG through them.

---

## One-liner to pass on

> "Drop `find-hardcodes/` into `.github/skills/`, type `/find-hardcodes` in Copilot Chat: it
> **runs a small script to gather all candidates → judges each → outputs the final list**; edit
> the CONFIG block in SKILL.md to choose what to scan, which values, and exclusions. Review results."
