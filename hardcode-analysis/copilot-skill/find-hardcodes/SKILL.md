---
name: find-hardcodes
description: >
  Find hardcoded group-member / business codes in source code (legacy AS/400 RPG/CL/COBOL/DDS
  or general code). Use when asked to locate where a value/code is written directly into the
  logic. Works in three steps: (1) gather every candidate by search, any encoding; (2) judge
  each candidate one by one; (3) output the final list. Configurable via the CONFIG block.
---

# Find hardcoded values

You are a careful code auditor. Find every place where a **business value / code is hardcoded**
into the logic, so it can be checked against a rewrite.

This is **best-effort assistance** — every result is a candidate for human review, not a
guarantee. Favour **recall** in step 1 (gather everything) and **precision** in step 2 (judge
honestly). Never invent a hit; every candidate must cite a real `file:line` you found by search.

---

## CONFIG — edit this block, then run. (Blank or `ANY` = the broad default.)

```
# WHAT VALUES / FIELD TO FIND
TARGET_VALUES   = ANY            # ANY = any hardcoded code/flag/magic literal.
                                 # Or a fixed list, e.g.: HAAA,HBBJ,HBCB,HSBC
VALUE_SHAPE     = ANY            # Optional hint, e.g. "4 letters starting with H", or a regex.
FIELD_PATTERNS  = GMAB,??GMAB    # The group member field name(s). ? = one char, * = many.
                                 # Bare GMAB AND the usual 2-char-prefix form (L1GMAB, ...).
                                 # Comma-separated. ANY = a value bound to any field counts.

# SCOPE — what to scan
INCLUDE_GLOBS   = **/*           # only scan paths matching these globs (comma-separated)
EXCLUDE_GLOBS   =                # skip these (e.g. **/test/**, **/generated/**)
EXCLUDE_EXTS    =                # skip these extensions (e.g. .md,.json,.log,.txt)
NAME_STARTS_WITH=                # only scan files/folders whose NAME starts with this
                                 #   (comma-separated, e.g. IB,GL -> IB107.RPGLE, GLxxx)

# SOURCE NOTES (legacy AS/400)
SEQ_PREFIX      = AUTO           # AUTO = ignore any leading run of digits/spaces (SEU
                                 #   sequence/date/change-id) when judging columns/comments.
EBCDIC_CCSID    =                # e.g. 937. Only affects X'..' hex literals (see step 1c).

# EXTRA EXCLUSIONS — free text, one rule per line. Obey these in step 2.
EXTRA_EXCLUDE   =
  # e.g. ignore single characters used as %EDITC edit codes ('X','Y')
  # e.g. ignore separators in message-text building
```

---

## STEP 1 — Gather ALL candidates (mechanical, high recall). Do NOT judge yet.

Apply scope from CONFIG (`INCLUDE_GLOBS`, `EXCLUDE_GLOBS`, `EXCLUDE_EXTS`, `NAME_STARTS_WITH`).
List the files you will scan; if scope is large, do it folder by folder and report progress.

Then collect every line that matches ANY of these — **regardless of file encoding** — using
workspace search (`#codebase`) or, if a terminal is available, `grep`/`rg`:

- **1a. Field has a value.** A `FIELD_PATTERNS` field appears with a quoted literal nearby:
  `... FIELD ... 'xxxx' ...` or `'xxxx' ... FIELD` — assignment (`MOVE`/`EVAL`/`Z-ADD`),
  comparison (`IF`/`WHEN`/`DOW`/`=`/`<>`/`EQ`/`NE`), substring (`%SUBST(FIELD:...)='..'`),
  or named constant / default (`dcl-c FIELD const('..')`, `... INZ('..')`).
- **1b. Target value appears.** If `TARGET_VALUES` is a list, every quoted occurrence of those
  values anywhere (e.g. `'HBCB'`), even with no field on the line.
- **1c. Hex form (EBCDIC).** Also search for each target value's EBCDIC-hex form, e.g.
  `X'C8C2C3C2'` for `HBCB`. Uppercase Latin letters are the same across EBCDIC code pages:
  `H`=C8 `A`=C1 `B`=C2 `C`=C3 `D`=C4 `F`=C6 `G`=C7 `J`=D1 `M`=D4 `P`=D7 `Q`=D8 `S`=E2 `T`=E3
  `U`=E4. (If `TARGET_VALUES = ANY`, just collect any `X'....'` literals near a field.)

Output the raw candidate list first — `file:line` + the line text — and say how many you found.
**Goal of step 1: miss nothing. Over-collecting is fine; step 2 filters.**

## STEP 2 — Judge each candidate one by one (precision). Give a verdict per candidate.

For EACH candidate from step 1, decide **hardcode: YES / NO** with a one-line reason, using:

**YES — it is a hardcode** when a literal and a field/constant are the two sides of the SAME
compare / assign / declaration:

| kind | example |
|------|---------|
| compare | `IF L1GMAB = 'HBCB'` |
| assign  | `MOVE 'HSBC' K7GMAB` / `EVAL L1GMAB = 'HBCB'` |
| const / default | `dcl-c W0gmab const('HSBC')` / `... INZ('HBCB')` |
| substring / prefix | `%SUBST(L1GMAB:1:2) = 'HB'` |
| hex | `IF L1GMAB = X'C8C2C3C2'` |
| bare literal | one of the target values appears but no field on the line (mark LOW) |

**NO — not a hardcode** (exclude):
- the line is a **comment** (fixed-form: leading digits/spaces + form-type letter + `*`/`/`,
  e.g. `10491H* ...`; free `//`; CL `/* */`; SQL `--`);
- it is a **field/variable name**, not a value (`GRPMBR_FLAG`, `HBCB_SW`);
- **field-to-field** assign/compare (`MOVE BFGMAB AGGMAB`, `IF A <> B`) — no literal;
- a **separator in string building** (`... + ' ' + %trim(FIELD) + '-' + ...`);
- a literal that belongs to a **different field** in a compound `AND`/`OR` test
  (in `IF (STATUS='1') AND (L1GMAB<>W3GMAB)` the `'1'` is STATUS's, not the field's);
- a **ubiquitous** token (company/library/program name) not next to a target field;
- anything matched by a rule in `EXTRA_EXCLUDE`.

Binding test: between the field and the literal there must be only "glue" — spaces, one
relational/assignment operator, `const(`/`inz(`, `%SUBST(...)` parens/colons/digits, or an `X`
hex marker. A `+`, another field, a comma, or another quote means **not bound** → NO (or LOW).

Confidence: **HIGH** = bound to a `FIELD_PATTERNS` field; **MEDIUM** = a target value but not
next to the field; **LOW** = weak / needs a human.

## STEP 3 — Final list

Output one consolidated table of the confirmed hardcodes (YES), one row per hit:

| file | line | value | form (text/hex) | kind | field | confidence | code (the one line) |
|------|------|-------|-----------------|------|-------|-----------|---------------------|

Show only the **single matched line**. Then a short summary: total candidates (step 1), how
many judged YES, HIGH vs MEDIUM vs LOW, and anything skipped or too large to read fully.

---

### Coverage note
An AI chat cannot read millions of lines at once. This works well for a small/medium scope;
for a very large codebase, narrow the scope with CONFIG and run folder by folder. For a
*guaranteed, repeatable* 100% scan, use the deterministic Python tool shipped alongside this
skill (parent `hardcode-analysis/`). This skill is the easy, shareable, best-effort version.
