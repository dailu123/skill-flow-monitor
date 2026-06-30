# Find hardcodes with Copilot — a shareable Skill

> 中文：[README.zh.md](./README.zh.md)

This is a **GitHub Copilot Skill** (a `.github/skills/` folder). Drop the folder into a repo and
you can ask Copilot Chat to find **hardcoded business values / codes** (branch/status/group
member, etc.). It **works out of the box** (finds as much as possible) and is customisable via a
config block at the top of `SKILL.md`.

> ⚠️ This is **best-effort assistance** — results are candidates for human review, not a
> guarantee. For a *repeatable, no-miss* full scan, use the deterministic Python tool that
> ships alongside it (parent folder `hardcode-analysis/`). This skill is the easy, shareable
> version.

## How it works (three steps)
1. **Gather all candidates** (mechanical search, any encoding): every place a group member
   field is assigned/compared, or a target value appears (incl. `X'..'` hex) — list them, no
   judging yet.
2. **Judge each candidate** one by one — is it a hardcode? verdict + reason (built-in rules).
3. **Final list** (confirmed hits table + summary).

---

## 1. How to use (pick one)

**Option A — as a Skill (recommended, reusable via `/`)**
1. Copy the whole [`find-hardcodes/`](./find-hardcodes/) folder into your repo's **`.github/skills/`**
   (i.e. `.github/skills/find-hardcodes/SKILL.md`).
2. In Copilot Chat (Agent mode) type `/find-hardcodes`, Enter; optionally add a scope, e.g.
   "scan sources/CHN_HUB_IB". The agent discovers the skill automatically on start.

**Option B — simplest, no setup**
1. Open Copilot Chat.
2. Paste the **entire content** of `find-hardcodes/SKILL.md`.
3. Add a line: "Apply the three steps above to `<your folder>` and output the table."

> **Do you need `copilot-instructions.md`? No.** That file is injected into *every* chat
> automatically — wrong for an on-demand task. A Skill is invoked on demand with `/`, which fits.

---

## 2. How to customise (edit the CONFIG block at the top)

Leave a field blank or `ANY` to keep the broad default. Common edits:

| Goal | Field | Example |
|------|-------|---------|
| Only a fixed set of values | `TARGET_VALUES` | `TARGET_VALUES = HAAA,HBBJ,HBCB,HSBC` |
| Hint the value shape | `VALUE_SHAPE` | `VALUE_SHAPE = 4 letters starting with H` |
| Which field the value binds to (prefix match) | `FIELD_PATTERNS` | `FIELD_PATTERNS = ??GMAB` (`?`=one char, `*`=many) |
| Only scan some paths | `INCLUDE_GLOBS` | `INCLUDE_GLOBS = sources/**, src/**` |
| Skip some paths | `EXCLUDE_GLOBS` | `EXCLUDE_GLOBS = **/test/**, **/generated/**` |
| Skip some extensions | `EXCLUDE_EXTS` | `EXCLUDE_EXTS = .md,.json,.log,.txt` |
| Only files/folders whose name starts with… | `NAME_STARTS_WITH` | `NAME_STARTS_WITH = IB,GL` |
| Host character set (affects hex) | `EBCDIC_CCSID` | `EBCDIC_CCSID = 937` |
| Add your own exclusions (plain language) | `EXTRA_EXCLUDE` | see below |

`EXTRA_EXCLUDE` is free text, one rule per line; Copilot obeys it:
```
EXTRA_EXCLUDE =
  ignore single characters used as %EDITC edit codes ('X','Y')
  ignore separators in message-text building
  ignore hits on the field W3SFRC
```

---

## 3. What it finds / ignores (built in)

**Counts** — a field and a literal are the two sides of the same compare/assign/declaration:
`IF L1GMAB='HBCB'`, `MOVE 'HSBC' K7GMAB`, `dcl-c W0gmab const('HSBC')`,
`%SUBST(L1GMAB:1:2)='HB'`, hex `X'C8C2C3C2'`.

**Ignores** — comments, field/variable names, field-to-field (`MOVE A B`), concatenation
separators (`+ ' ' +`), a value belonging to a different field in a compound test, ubiquitous
company/library names, and anything in your `EXTRA_EXCLUDE`.

Output is a table: file, line, value, form (text/hex), kind, field, confidence (HIGH/MEDIUM/LOW),
and the single matched line.

---

## 4. One-liner to pass on

> "Drop the `find-hardcodes/` folder into `.github/skills/`, type `/find-hardcodes` in Copilot
> Chat: it **gathers all candidates → judges each one → outputs the final list**; edit the
> config block at the top of SKILL.md to choose what to scan, what to skip, which values to
> find, and add exclusions. Always review the results."
