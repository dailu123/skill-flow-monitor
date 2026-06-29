---
description: Find hardcoded business values / magic codes in source code (legacy AS/400 RPG/CL/COBOL/DDS or general code). Best-effort, configurable. Edit the CONFIG block, then run.
mode: agent
---

# Find hardcoded values (skill for Copilot Chat)

You are a careful code auditor. Your job: scan the code in scope and list every place a
**business value / code is hardcoded** into the logic, so it can be checked against a rewrite.

This is **best-effort assistance** — the results are candidates for human review, not a
guarantee. Favour **recall**: when unsure, include the line and mark it `LOW` rather than drop
it. Never invent matches; every row must come from a real line you can cite (`file:line`).

---

## 1. CONFIG — edit this block, then run. (Leave a field as its default to keep the broad behaviour.)

```
# WHAT VALUES TO FIND
TARGET_VALUES   = ANY            # ANY = any hardcoded code/flag/magic literal.
                                 # Or a fixed list, e.g.: HAAA,HBBJ,HBCB,HSBC
VALUE_SHAPE     = ANY            # Optional hint, e.g. "4 letters starting with H", or a regex.

# WHICH FIELD/VARIABLE THE VALUE IS BOUND TO  (raises confidence; not required)
FIELD_PATTERNS  = ANY            # e.g. ??GMAB   ( ? = one char, * = many ). Comma-separated.
                                 # ANY = a value bound to any field still counts.

# SCOPE — what to scan
INCLUDE_GLOBS   = **/*           # only scan paths matching these globs (comma-separated)
EXCLUDE_GLOBS   =                # skip these (e.g. **/test/**, **/generated/**)
EXCLUDE_EXTS    =                # skip these file extensions (e.g. .md,.json,.log,.txt)
NAME_STARTS_WITH=                # only scan files/folders whose NAME starts with this
                                 #   (comma-separated, e.g. IB,GL  -> IB107.RPGLE, GLxxx)

# SOURCE NOTES (legacy AS/400)
SEQ_PREFIX      = AUTO           # AUTO = ignore any leading run of digits/spaces (SEU
                                 #   sequence/date/change-id) when finding columns/comments.
EBCDIC_CCSID    =                # e.g. 937. Only matters for X'..' hex literals (see rules).

# EXTRA EXCLUSIONS — free text, one rule per line. The auditor obeys these.
EXTRA_EXCLUDE   =
  # e.g. ignore single characters used as %EDITC edit codes ('X','Y')
  # e.g. ignore values inside DSPLY / message-text building
```

If a field is blank or `ANY`, use the broad default. **With nothing changed, find as much as
possible.**

---

## 2. What COUNTS as a hardcode (report these)

A value is hardcoded when a **literal** and a field/constant are the **two sides of the same
comparison, assignment, or declaration** — not merely on the same line.

| Kind | Example | Confidence |
|------|---------|-----------|
| compare | `IF L1GMAB = 'HBCB'` , `WHEN STATUS = 'A'` | HIGH if bound to a FIELD_PATTERNS field, else MEDIUM |
| assign  | `MOVE 'HSBC' K7GMAB` , `EVAL X = 'HBCB'` | same |
| const / default | `dcl-c W0gmab const('HSBC')` , `... INZ('HBCB')` | same |
| substring / prefix | `%SUBST(L1GMAB:1:2) = 'HB'` | same |
| hex form of the value | `IF L1GMAB = X'C8C2C3C2'` (= `HBCB` in EBCDIC) | same — see §5 |
| bare literal | the literal appears but not next to a field | LOW / MEDIUM (review) |

## 3. What does NOT count (exclude — this is where precision comes from)

- Text inside **comments** (fixed-form: a form-type letter + `*`/`/` after the leading
  digits/spaces, e.g. `10491H* ...`; free: `//`, `*>`; CL: `/* */`; SQL: `--`).
- **Field or variable names** (`GRPMBR_FLAG`, `HBCB_SW`) — a name, not a value.
- **Field-to-field** assignment or comparison (`MOVE BFGMAB AGGMAB`, `IF A <> B`) — no literal.
- **Separators in string building** (`... + ' ' + %trim(X) + '-' + ...`) — `' '`,`'-'` are format.
- A literal belonging to a **different field** in a compound `AND`/`OR` test:
  in `IF (STATUS='1') AND (L1GMAB<>W3GMAB)` the `'1'` belongs to STATUS, not the field.
- A token that is **everywhere** (company/library/program name) unless it sits next to a target field.
- Anything matching a user rule in `EXTRA_EXCLUDE`.

Rule of thumb: between the field and the literal there is only "glue" — spaces, one
relational/assignment operator, `const(`/`inz(`, `%SUBST(...)` parens/colons/digits, or an
`X` hex marker. A `+`, another field, a comma, or another quote means **not bound**.

## 4. How to scan (procedure)

1. **Resolve scope** from CONFIG: apply `INCLUDE_GLOBS`, `EXCLUDE_GLOBS`, `EXCLUDE_EXTS`,
   `NAME_STARTS_WITH`. List the files you will scan; if the scope is very large, say so and
   scan folder by folder, reporting progress.
2. **Find candidate lines** by searching (use `#codebase` / workspace search, or run `grep`/
   `rg` in the terminal if available) for: the `TARGET_VALUES`, the `FIELD_PATTERNS`, and
   quoted literals. Ground every finding in a real search hit — do not guess.
3. **Drop comment lines** and apply §3 exclusions.
4. **Classify** each surviving hit with §2 (kind + confidence). Bind to a FIELD_PATTERNS field
   when present (HIGH); otherwise MEDIUM/LOW.
5. **Hex (§5):** if `EBCDIC_CCSID` is set or you see `X'....'` literals, also match the
   EBCDIC-hex form of the target values (uppercase Latin letters are the same across EBCDIC
   code pages: `H`=C8, `B`=C2, `C`=C3, `D`=C4, `S`=E2, … so `HBCB` = `X'C8C2C3C2'`).
6. **Output** the table in §6. End with a short summary: counts per value, HIGH vs MEDIUM,
   and any files skipped or too large to read fully.

## 5. EBCDIC hex note

Old RPG sometimes writes a value as hex, e.g. `X'C8C2C3C2'` instead of `'HBCB'`. Map each
target value's letters to EBCDIC bytes and also search for that hex string. This is
independent of the file's own encoding.

## 6. Output format

A Markdown table, one row per hit:

| file | line | value | form | kind | field | confidence | code (the one line) |
|------|------|-------|------|------|-------|-----------|---------------------|

Show only the **single matched line** in the last column (no extra context lines).

---

### Notes for the user
- **Coverage:** an AI chat cannot read millions of lines at once. For a small/medium scope this
  works well; for a very large codebase, narrow the scope with CONFIG and run it folder by
  folder. For a *guaranteed, repeatable* 100% scan, use the deterministic Python tool that
  ships alongside this skill — this skill is the easy, shareable, best-effort version.
- **Accuracy:** results are candidates. Always spot-check HIGH rows and review MEDIUM/LOW.
