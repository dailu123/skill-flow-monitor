---
name: find-hardcodes
description: >
  Find hardcoded group-member / business codes in source (legacy AS/400 RPG/CL/COBOL/DDS or
  general code). Use when asked to locate where a value is written directly into the logic.
  Three steps: (1) run a fixed PowerShell command to gather all candidate lines (scales to
  millions of lines, no extra tools); (2) judge each candidate; (3) output the final list.
  Configurable via the CONFIG block.
---

# Find hardcoded values

You are a careful code auditor. Goal: list every place a **business value / code is hardcoded**
into the logic, so it can be checked against a rewrite. This is **best-effort assistance** —
results are candidates for human review, not a guarantee.

The job is split so it scales and stays honest:
1. **Gather** every candidate with one deterministic PowerShell command (recall — miss nothing).
2. **Judge** each candidate one by one (precision — is it really a hardcode?).
3. **List** the confirmed results.

---

## CONFIG — edit, then run. (Blank / `ANY` = the broad default.)

```
TARGET_VALUES   = ANY            # ANY, or a fixed list e.g. HAAA,HBBJ,HBCB,HSBC
FIELD_PATTERNS  = GMAB,??GMAB    # field name(s) the value binds to. ?=one char, *=many.
                                 #   bare GMAB AND 2-char-prefix (L1GMAB,...). ANY = any field.
INCLUDE_GLOBS   = **/*           # only scan these
EXCLUDE_GLOBS   =                # skip these (e.g. **/test/**)
EXCLUDE_EXTS    =                # skip these extensions (e.g. .md,.json,.log)
NAME_STARTS_WITH=                # only files/folders whose name starts with this (e.g. IB,GL)
EXTRA_EXCLUDE   =                # free-text rules, one per line, obeyed in STEP 2
```

---

## STEP 1 — Gather all candidates with PowerShell. Do NOT judge yet.

Everyone on Windows has PowerShell — no Python or extra install. Run this **fixed** pipeline
(set `$Src`; edit `$Field`/filters only if the CONFIG differs). It walks the source, keeps lines
that contain a group-member field **and** a quoted literal, drops comment lines (any sequence-
number prefix width), and writes `candidates.csv`. It over-collects on purpose.

```powershell
# ---- set these from CONFIG ----
$Src     = "C:\path\to\source"          # SOURCE ROOT to scan
$Out     = "candidates.csv"
# FIELD_PATTERNS = GMAB,??GMAB  -> bare GMAB or a 2-char prefix; '_' counts as an identifier char
$Field   = '(?<![A-Za-z0-9_@#$])(?:[A-Za-z0-9_@#$]{2})?GMAB(?![A-Za-z0-9_@#$])'
$Comment = '^[0-9 ]*[HFDICOPJ][*/]'     # fixed-form comment line, any prefix width

Get-ChildItem -Path $Src -Recurse -File |
  # ---- optional scope filters (uncomment / edit to match CONFIG) ----
  # Where-Object { $_.Name -like 'IB*' -or $_.Directory.Name -like 'IB*' } |   # NAME_STARTS_WITH
  # Where-Object { $_.Extension -notin '.md','.json','.log' } |                # EXCLUDE_EXTS
  Select-String -Pattern $Field |
  Where-Object { $_.Line.Contains("'") -and $_.Line -notmatch $Comment } |
  Select-Object @{n='file';e={$_.Path}}, LineNumber, @{n='code';e={$_.Line.Trim()}} |
  Export-Csv -NoTypeInformation -Encoding UTF8 $Out

Write-Host ("candidates -> {0}  (rows: {1})" -f $Out, (Import-Csv $Out).Count)
```

Then open `candidates.csv` (columns `file,LineNumber,code`) — that is your candidate set for
STEP 2. Report how many candidates were found.

**Adjusting `$Field` from CONFIG (only if you change FIELD_PATTERNS):**
- Different field name `FOO` with the same bare/2-prefix rule: replace `GMAB` with `FOO`.
- An explicit list of exact names: `'(?<![A-Za-z0-9_@#$])(NAME1|NAME2)(?![A-Za-z0-9_@#$])'`.
- **Search by value instead** (TARGET_VALUES set, FIELD_PATTERNS = ANY): use
  `$Field = "'(HAAA|HBBJ|HBCB|HSBC)'"` (the values, quoted). For the EBCDIC hex form add e.g.
  `|X'C8C2C3C2'` (HBCB). `Select-String` is case-insensitive by default.

> Notes: works on text source (as it appears in the editor). If a file is raw EBCDIC, convert it
> to text first — the hex form `X'..'` is plain ASCII and is still found. On millions of lines the
> command may take a few minutes; that is normal.

---

## STEP 2 — Judge each candidate one by one

Read `candidates.csv`. For EACH row, decide **hardcode: YES / NO** with a one-line reason.

**YES** — a literal and a field/constant are the two sides of the SAME compare / assign / declare:

| kind | example |
|------|---------|
| compare | `IF L1GMAB = 'HBCB'` |
| assign  | `MOVE 'HSBC' K7GMAB` / `EVAL L1GMAB = 'HBCB'` |
| const / default | `dcl-c W0gmab const('HSBC')` / `... INZ('HBCB')` |
| substring / prefix | `%SUBST(L1GMAB:1:2) = 'HB'` |
| hex | `IF L1GMAB = X'C8C2C3C2'`  (= `HBCB`) |
| bare literal | a TARGET value appears but no field on the line (mark LOW) |

**NO** — exclude:
- **field-to-field** (`MOVE BFGMAB AGGMAB`, `IF A <> B`) — no literal at all;
- a **separator in string building**: `... + ' ' + %trim(L1GMAB) + '-' + %editc(X:'X')` — the
  `' '`/`'-'`/`'X'` are formatting, joined by `+`, not bound to the field;
- a literal that belongs to a **different field** in a compound `AND`/`OR` test —
  in `IF (STATUS='1') AND (L1GMAB<>W3GMAB)` the `'1'` is STATUS's, not the field's;
- a **field/variable name**, not a value (`GMAB_FLAG`);
- a **ubiquitous** token (company/library/program name) not next to a target field;
- anything matching a rule in `EXTRA_EXCLUDE`.

**Binding test (the core rule):** between the field token and the literal there must be only
"glue" — spaces, one relational/assignment operator (`= <> < > EQ NE …`), `const(`/`inz(`,
`%SUBST(...)` parens/colons/digits, or an `X` hex marker. A `+`, another field, a comma, or
another quote ⇒ **NOT bound** ⇒ NO (or LOW).

**Confidence:** HIGH = bound to a `FIELD_PATTERNS` field · MEDIUM = a target value but not next
to the field · LOW = weak / needs a human.

(For large candidate sets, judge in batches and keep a running tally.)

## STEP 3 — Final list

Output one consolidated table of the confirmed hardcodes (YES):

| file | line | value | form (text/hex) | kind | field | confidence | code (the one line) |
|------|------|-------|-----------------|------|-------|-----------|---------------------|

Show only the single matched line. End with a summary: candidates gathered (STEP 1), judged YES,
HIGH/MEDIUM/LOW counts, and anything skipped.

---

### Note on accuracy
Every result is a candidate for human review. Spot-check HIGH, review MEDIUM/LOW. The PowerShell
step is deterministic (same input → same candidates); the judging step is the AI's best effort.
