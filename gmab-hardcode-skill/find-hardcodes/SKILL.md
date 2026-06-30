---
name: find-hardcodes
description: >
  Find hardcoded group-member / business codes in source (legacy AS/400 RPG/CL/COBOL/DDS or
  general code). Use when asked to locate where a value is written directly into the logic.
  Three steps: (1) generate and run a small search script (your choice of PowerShell, default,
  or Python for raw EBCDIC) that follows the precise spec below to gather all candidate lines;
  (2) judge each candidate; (3) output the final list. Configurable via the CONFIG block.
---

# Find hardcoded values

You are a careful code auditor. Goal: list every place a **business value / code is hardcoded**
into the logic, so it can be checked against a rewrite. This is **best-effort assistance** —
results are candidates for human review, not a guarantee.

The job is split so it scales and stays honest:
1. **Gather** candidates with a small script you generate (recall-first — over-collect; see the
   recall note in STEP 1 for what maximises coverage and what it still can't catch).
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

## STEP 1 — Generate and run a gather script. Do NOT judge yet.

**Write the script yourself** — do not expect one to be provided. Prefer **Windows PowerShell**
(no install, everyone has it). Use **Python** only if some files are raw **EBCDIC** binary
(PowerShell can't decode those) or PowerShell isn't available. The script must produce a CSV
called `candidates.csv` and must implement **exactly** the rules below. (A human may edit any
rule here to change behaviour.)

**A. Which files to scan (from CONFIG)**
- Walk the source root recursively.
- Keep only paths matching `INCLUDE_GLOBS`; drop any matching `EXCLUDE_GLOBS`.
- Drop files whose extension is in `EXCLUDE_EXTS`.
- If `NAME_STARTS_WITH` is set, keep a file only if its name — or one of its parent folder names —
  starts with one of the listed prefixes.
- Skip binary files (any file containing a NUL byte).

**B. Reading / encoding**
- Read each file as text. If it is not valid UTF-8 and looks like EBCDIC (the byte 0x40 — the
  EBCDIC space — dominates), decode it as code page **037 / cp037**. The target codes are
  uppercase letters, which are identical across EBCDIC code pages, so this is safe even for a
  CCSID-937 host.

**C. Emit a line as a candidate when ALL of these are true** (over-collect — recall first):
1. **It is not a comment.** A comment line = an optional leading run of digits and spaces (the
   SEU sequence-number / date / change-id prefix — *any* width), then an RPG form-type letter
   (`H` `F` `D` `I` `C` `O` `P` `J`) immediately followed by `*` or `/`. Examples of comments to
   skip: `10491H* ...`, `54900000000017453C* ...`, `     D* ...`. Also drop free-form `//`,
   COBOL `*>`, and SQL `--` (ignore everything from that marker to end of line).
2. **It references the group-member field.** Match a **whole-word** token that is either bare
   `GMAB`, **or** exactly **two** identifier characters followed by `GMAB`. Identifier characters
   are `A–Z a–z 0–9 _ @ # $`. "Whole-word" means the characters immediately before and after the
   token are **not** identifier characters. So these MATCH: `GMAB`, `L1GMAB`, `K7GMAB`, `W0gmab`
   (case-insensitive); these do NOT: `GMAB_FLAG` (trailing `_`), `ABCGMAB` (3-char prefix),
   `chkGmab` (preceded by a letter). Matching is case-insensitive.
   - If `FIELD_PATTERNS` differs, follow it instead: `?` = one identifier char, `*` = any number,
     comma = OR. If `FIELD_PATTERNS = ANY`, drop this requirement (match any field).
3. **It contains a quoted string literal** — a single quote `'` appears on the line. This also
   covers hex literals such as `X'C8C2C3C2'`.

**D. Also (only if `TARGET_VALUES` is a list, in addition to C):** emit any line containing one of
those values inside quotes (e.g. `'HBCB'`), and any line containing the value's **EBCDIC hex**
inside `X'...'`. Build the hex by mapping each letter to its EBCDIC byte:
`H=C8 A=C1 B=C2 C=C3 D=C4 F=C6 G=C7 J=D1 M=D4 P=D7 Q=D8 S=E2 T=E3 U=E4` (digits `0–9` = `F0–F9`).
So `HBCB` → `X'C8C2C3C2'`.

**E. Output** `candidates.csv` with columns `file,line,code`, where `code` is the matched line,
trimmed, with control characters removed. Print how many candidate lines were found. On millions
of lines this may take a few minutes — that is fine.

Open `candidates.csv` — that is your candidate set for STEP 2. Report the count.

**Recall note (be honest about coverage).** The gather is *deterministic* (same input → same
output) but not *exhaustive*. The rules above catch a hardcode only when a field **and** a quote
are on the **same line**. To maximise recall:
- If `TARGET_VALUES` is a **known, closed set**, LIST it (do not leave it `ANY`). Then rule **D**
  also searches for the exact values + their EBCDIC hex **anywhere**, catching cases where the
  value and the field are on different lines (reached via a work field, parameter, array, etc.).
- Known blind spots that even this won't catch — flag them for human/sample review:
  multi-line / continued statements (`IF GMAB =` then `'HBCB'` on the next line); the value built
  up by concatenation; a value stored only in data (DTAARA / DDS default), not in code; or a value
  written in an encoding other than text or `X'..'` hex. No pure scan guarantees 100%.

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
Every result is a candidate for human review. Spot-check HIGH, review MEDIUM/LOW. The gather step
is deterministic (same input → same candidates); the judging step is the AI's best effort.
