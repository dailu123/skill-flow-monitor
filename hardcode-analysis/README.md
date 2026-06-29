# Hardcode Analysis — GMAB matcher

> 中文版见 [README.zh.md](./README.zh.md)

Deterministically locate where the 15 group member (GMAB) values are **hardcoded** in an
IBM i (AS/400) banking codebase, producing a reproducible, structured list for Java-rewrite
parity verification.

**Pure Python standard library. Runs on Windows. Recall is guaranteed by rules — no LLM in
the recall path.** An LLM may optionally (a) classify MEDIUM rows afterwards and (b) author
new detection patterns (see the skill), but it never reads source line-by-line to "find"
hardcodes.

## Why rules, not line-by-line AI reading

This is a deterministic extraction task, not a judgement task. Line-by-line AI reading is
not reproducible, risks missing lines, and its cost scales with code size. Recall must be
100% by construction; the LLM is at most an optional final annotator.

## Modules (data flow)

1. `literal_extractor.py` — **constraint 1**: sniff encoding per file (strict UTF-8 first,
   then EBCDIC/latin-1), then a tolerant lexer extracts **string literals** (single/double
   quote, `''` escape, comment stripping, `X'..'` hex, continuation). Never greps raw lines;
   never dispatches by file name.
2. `value_matcher.py` — **constraints 2/3**: anchor A. Exact match of the 15 values
   (case-sensitive, full 4 chars) plus the EBCDIC hex form (`build_hex_table`, cp037).
3. `field_matcher.py` — **constraints 4/5/6**: logical-statement segmentation (EXEC SQL
   block to `;`, free continuation, fixed per line) and whether a literal is **adjacent to
   the group member field** (token boundary, so `GRPMBR_FLAG` is not a false hit).
4. `patterns.py` — **extensibility**: an engine for additional, user-supplied detection
   patterns loaded from JSON (`--patterns`). The two core anchors stay hardcoded; patterns
   add recall (a routing helper call, an alternate encoding, a new prefix idiom) without
   editing code. The LLM only authors the regex; matching stays deterministic.
5. `merge_dedup.py` — **constraint 7**: union A ∪ B ∪ patterns, de-dup by
   `program+member+line+col+value`. HSBC kept only when field-adjacent. HIGH = field-adjacent,
   MEDIUM = not.
6. `report.py` — writes `gmab_hits.csv` and `gmab_summary.md` (per-value counts, ASCII/HEX,
   HIGH/MEDIUM, and the out-of-list candidates).

## Before you run

1. **Precheck**: on IBM i, run `hardcode_matcher/precheck.sql` to confirm whether the 15
   values are the entire real data domain, and to find the **real column name / aliases**
   of the group member field.
2. Fill in `hardcode_matcher/config.py`: `FIELD_NAMES` (real column name(s)), and
   `EBCDIC_CODEC` if not 037. `GMAB_VALUES` is a **closed enumeration** — a 16th value is
   merged only after human confirmation; the tool never changes the set on its own.

## Run (Windows)

```
python -m hardcode_matcher.run --src <HUB source root> --out gmab_out \
    --fields "??GMAB" --ccsid cp037 \
    --patterns patterns/custom_patterns.example.json
```

Argument meaning:

- `--src` — source root to scan (recursive, all files, no file-name dispatch). Point it at
  **HUB source only** (do not mix in this tool or other-language files, or you will extract
  unrelated literals).
- `--out` — output directory for `gmab_hits.csv` + `gmab_summary.md`.
- `--fields` — the group member **column name(s)**, comma-separated, used for anchor B
  (field adjacency). Supports wildcards: `?` = one identifier char, `*` = many. In HUB the
  column has a **2-char variable prefix**, so use `"??GMAB"` (matches `01GMAB`, `bkGMAB`,
  …, but not bare `GMAB`, a 3-char prefix, or `xxGMAB_FLAG`).
- `--ccsid` — EBCDIC codec (default `cp037` = CCSID 037). Used both to decode raw EBCDIC
  source and to compute each value's EBCDIC bytes for the `X'..'` hex form. Change it if the
  host CCSID differs (e.g. 1388 — see Known boundaries).
- `--exts` — optional extension filter; default scans everything.
- `--patterns` — optional custom-pattern JSON; omit to use only anchors A/B.

## Output columns

`program, member, line, col, matched_value, match_form (ASCII/HEX), anchor (A/B),
statement (±2 lines), field_adjacent, confidence (HIGH/MEDIUM), lang, pattern`

## Extending with new patterns

When you (or a teammate) discover another hardcoding idiom, add a pattern to a JSON file
instead of editing code. Each pattern is a regex (with a named `value` group) plus metadata.
See `patterns/custom_patterns.example.json` and the skill
[`../SKILL_hardcode-analysis.md`](../SKILL_hardcode-analysis.md), which guides an LLM to
author a validated pattern entry (and never to widen the GMAB value set without confirmation).

## Self-check

```
python -m hardcode_matcher.samples.selftest
```

Validates: fixed-form RPG column numbers, `''` escape not terminating the string early,
comment stripping (col-7 `*`, `//`, `*>`, `--`, `/* */`), EBCDIC file decode,
`X'C8C2C3C2'`→HBCB hex match, the `%SUBST(GRPMBR:1:2)='HB'` prefix going to anchor B,
HSBC kept-when-field-adjacent / dropped otherwise, `GRPMBR_FLAG` not counted as the field,
and the custom-pattern engine.

## Real-world IBM i source notes

- **SEU seq+date prefix.** Members exported with the sequence number + change date carry a
  12-char numeric prefix on every record (`000400250811     C ... IF L1GMAB = 'HBCB'`),
  which shifts the fixed-form columns. The extractor auto-detects this (lines starting with
  12 digits) and accounts for it so comments strip correctly; force it with
  `config.SEQ_PREFIX_WIDTH`. Without this, an apostrophe in an unstripped comment
  (e.g. `Customer's DCN`) would open a runaway string and hide the real values.
- **Clause-level binding (precision).** Anchor B marks a literal as a GMAB hardcode only
  when it shares the same `AND`/`OR` clause as a GMAB field — so
  `IF (L1STUS='1') AND (L1GMAB<>W3GMAB)` and field-to-field comparisons are NOT reported,
  while `IF L1GMAB='HBCB'`, `MOVE 'HSBC' K7GMAB`, and `%SUBST(L1GMAB:1:2)='HB'` are.
- Quoted literals are closed at end of line (they do not span physical lines), bounding any
  malformed/unterminated string.

## Known boundaries (assumptions stated up front)

- CCSID 1388 (host GBK) has no built-in Python codec; it needs a custom map. Default is 037.
- Extraction is **lexical**, not a full parse tree; an extreme value split across continuation
  lines is handled by the "unterminated string joins the next line" safety net.
- The LLM is only an optional **post** step (classify MEDIUM rows; author patterns). It must
  be batched and fed literal slices, never whole files; recall does not depend on it.
