---
name: hardcode-analysis
description: >
  Add a new detection pattern to the GMAB hardcode matcher (hardcode-analysis/) without
  editing code. Given a description or an example of a hardcoding idiom found in the AS/400
  (RPG / CL / COBOL / SQLRPGLE) source, author one validated JSON pattern entry, test it on
  a snippet, and append it to a custom_patterns.json file. Recall stays deterministic — you
  write the regex, the engine matches.
---

# Hardcode Analysis — add-pattern skill

The GMAB hardcode matcher (`hardcode-analysis/`) locates where 15 closed-set group member
values are hardcoded in AS/400 source, for Java-rewrite parity. Two anchors are hardcoded
in the tool: **A** (exact value + EBCDIC hex) and **B** (literal adjacent to the group
member field). This skill covers the **third, extensible layer**: experience-driven custom
patterns loaded from JSON via `--patterns`.

Use this skill when someone says: *"the matcher also needs to catch <idiom>"*, e.g. a
routing-helper call, an alternate encoding, a new prefix/truncation comparison, a copybook
constant.

## Hard rules (do not break)

1. **Never widen or narrow the GMAB value set.** The 15 values in `config.GMAB_VALUES` are a
   closed enumeration. If an idiom implies a 16th value, surface it as an out-of-list
   candidate and ask the human to confirm before any change to the set.
2. **You author the regex; the engine matches.** Do not "read source line-by-line to find
   hardcodes." Recall must stay deterministic and reproducible.
3. **Match must not land in comments.** The engine runs patterns on comment-stripped code
   (strings preserved), one physical line at a time. Design single-line regexes.
4. **Preserve HSBC handling.** `HSBC` is dropped unless field-adjacent; do not write a
   pattern that re-floods HSBC noise. If a pattern can emit HSBC, it must be a genuine
   field-reference idiom (set `anchor: "B"`).

## Pattern JSON schema

Append one object to the patterns file (a JSON list, or `{"patterns": [...]}`):

```json
{
  "name":        "routing_helper_call",
  "description": "GMAB value passed to chkGrpMbr()/getGrpRoute() helper",
  "regex":       "(?i)(?:chkGrpMbr|getGrpRoute)\\(\\s*'(?P<value>H[A-Z0-9]{3})'",
  "anchor":      "B",
  "match_form":  "ASCII",
  "confidence":  "HIGH",
  "lang":        "any"
}
```

- `name` — unique, snake_case.
- `regex` — capture the detected value in a named group `(?P<value>...)`. If omitted, the
  whole match is the value. Remember JSON string escaping (`\\(`, `\\s`).
- `anchor` — `"A"` (value form) or `"B"` (field-reference idiom). Default `"B"`.
- `match_form` — `"ASCII"` or `"HEX"`. Default `"ASCII"`.
- `confidence` — `"HIGH"`, `"MEDIUM"`, or `"AUTO"` (AUTO = HIGH iff the line is
  field-adjacent, else MEDIUM). Use `"AUTO"` unless the idiom itself is strong evidence.
- `lang` — optional report-only label.

## Authoring procedure

1. **Get a concrete example** of the idiom (one or two source lines).
2. **Write the regex** against the comment-stripped code form. Anchor it tightly so it does
   not over-match (e.g. require the helper name, the `(`, the quote).
3. **Validate** by loading and running it on the example before committing:
   ```
   cd hardcode-analysis
   python -c "from hardcode_matcher import patterns as P; \
import json,io; \
pat=P.load_patterns('patterns/custom_patterns.example.json'); \
print([p.name for p in pat])"
   ```
   or add the example line to `hardcode_matcher/samples/SAMPLE_RPG_FIXED.rpg` and run
   `python -m hardcode_matcher.samples.selftest`, confirming the new row appears with the
   right value/anchor/confidence and that nothing else changed.
4. **Append** the validated object to the project's `custom_patterns.json`
   (copy `patterns/custom_patterns.example.json` as a starting point).
5. Re-run the full matcher with `--patterns custom_patterns.json`.

## What NOT to do

- Do not paste whole source files to an LLM and ask it to find hardcodes.
- Do not author a pattern that matches inside comments or that broadens the value set.
- Do not change `config.GMAB_VALUES`, the anchors, or the dedup key to make a pattern "fit."
