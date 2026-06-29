# What the GMAB Hardcode Scan Looks For (plain-language rules)

> 中文版见 [RULES.zh.md](./RULES.zh.md). For the technical README see [README.md](./README.md).

**Goal.** Find every place in the HUB (AS/400) source where a *group member code* is
written directly into the program logic ("hardcoded"), so the Java rewrite can be checked
for the same behaviour. The scan is rule-based and repeatable — it does not rely on AI
reading the code, so the same source always produces the same list.

**The codes we look for** — a closed set of 15 values, all 4 characters, all starting with `H`:

```
HAAA  HBBJ  HBCB  HBCD  HBCF  HBCQ  HBDP  HBFU  HBGD  HBHT  HBHU  HBMC  HBSD  HBSH  HSBC
```

The group member field in HUB is named `??GMAB` (two variable characters + `GMAB`,
e.g. `L1GMAB`, `K7GMAB`).

---

## Counts as a hardcode (reported)

| # | Pattern | Example |
|---|---------|---------|
| 1 | The group member field is **compared** to a fixed value | `IF L1GMAB = 'HBCB'` |
| 2 | A fixed value is **assigned** to the group member field | `MOVE 'HSBC' K7GMAB` / `EVAL L1GMAB = 'HBCB'` |
| 3 | **Part of** the field is compared to a fixed value (prefix/truncation) | `%SUBST(L1GMAB:1:2) = 'HB'` |
| 4 | The value is written in **hexadecimal** (same value, different form) | `IF L1GMAB = X'C8C2C3C2'`  (= `HBCB`) |
| 5 | One of the 15 values appears as a **literal anywhere**, even without the field nearby | `MOVE 'HBCB' WRKFLD` |

Each hit is graded:

- **HIGH** — the value is directly compared/assigned to the group member field (cases 1–4).
- **MEDIUM** — the value appears but is not next to the field (case 5); routed to manual review
  (it may reach the field indirectly via an array, parameter or work field).

---

## Does NOT count (excluded, to avoid noise)

| Pattern | Example | Why excluded |
|---------|---------|--------------|
| Text in **comments** | `* HBCB means branch X` | not executable code |
| **Field or variable names** | `GRPMBR_FLAG`, `HBCB_SW` | a name, not a value |
| **Field-to-field** assignment | `MOVE BFGMAB AGGMAB` | no fixed value involved |
| **Field-to-field** comparison | `IF L1GMAB <> W3GMAB` | comparing two fields, not a hardcode |
| Separators in **string building** | `... + ' ' + %trim(L1GMAB) + '-' + ...` | `' '`/`'-'` are formatting, not values |
| A value belonging to **another field** in a compound test | `IF (L1STUS='1') AND (L1GMAB<>W3GMAB)` | `'1'` belongs to `L1STUS`, not the field |
| **`HSBC`** appearing in copyright / library / program names | `Copyright HSBC 2024` | kept only when next to the field (otherwise pure noise) |

The rule behind the exclusions: a value is a hardcode only when it and the group member field
are the **two sides of the same comparison or assignment** — not merely on the same line.

---

## What you get

- **`gmab_hits.csv`** — one row per hit: program, member, line, column, the value, ASCII/hex,
  the surrounding code, whether it is next to the field, and HIGH/MEDIUM confidence.
- **`gmab_summary.md`** — counts per value (and ASCII vs hex, HIGH vs MEDIUM), plus a list of
  "out-of-list" values found next to the field (candidates for a 16th code / dirty data).

## Extensible

If we later find a new way the codes are hardcoded (e.g. passed into a specific helper
routine), we add one rule for it without changing the engine. Recall stays rule-based and
repeatable.

## Notes / assumptions

- Source CCSID is **937** (Traditional Chinese host). The 15 codes are uppercase Latin
  letters, which are encoded identically across EBCDIC code pages, so the hexadecimal check
  (case 4) is unaffected by the CCSID.
- Source members carry a 12-character sequence-number + date prefix; the scan accounts for it
  so comments and columns line up correctly.
