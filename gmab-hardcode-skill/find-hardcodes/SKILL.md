---
name: find-hardcodes
description: >
  Find hardcoded group-member / business codes in source (legacy AS/400 RPG/CL/COBOL/DDS or
  general code). Use when asked to locate where a value is written directly into the logic.
  Self-contained: STEP 1 writes & runs a small script to gather all candidates (any encoding,
  scales to millions of lines); STEP 2 judges each candidate; STEP 3 outputs the final list.
  Configurable via the CONFIG block.
---

# Find hardcoded values

You are a careful code auditor. Goal: list every place a **business value / code is hardcoded**
into the logic, so it can be checked against a rewrite. This is **best-effort assistance** —
results are candidates for human review, not a guarantee.

The job is split so it scales and stays honest:
1. **Gather** every candidate with a deterministic script (recall — miss nothing).
2. **Judge** each candidate one by one (precision — is it really a hardcode?).
3. **List** the confirmed results.

---

## CONFIG — edit, then run. (Blank / `ANY` = the broad default.)

```
TARGET_VALUES   = ANY            # ANY, or a fixed list e.g. HAAA,HBBJ,HBCB,HSBC
FIELD_PATTERNS  = GMAB,??GMAB    # field name(s) the value binds to. ?=one char, *=many.
                                 #   bare GMAB AND 2-char-prefix (L1GMAB,...). ANY = any field.
INCLUDE_GLOBS   = **/*           # only scan these (comma-separated)
EXCLUDE_GLOBS   =                # skip these (e.g. **/test/**, **/generated/**)
EXCLUDE_EXTS    =                # skip these extensions (e.g. .md,.json,.log)
NAME_STARTS_WITH=                # only files/folders whose name starts with this (e.g. IB,GL)
EBCDIC_CCSID    = cp037          # host code page for X'..' hex (937 letters == cp037, ok)
EXTRA_EXCLUDE   =                # free-text rules, one per line, obeyed in STEP 2
```

---

## STEP 1 — Gather all candidates (run a script). Do NOT judge yet.

This skill ships `gather_candidates.py` (a single stdlib-only file, shown in full below). It
walks the source, skips comments (any sequence-prefix width), decodes any encoding (UTF-8 /
EBCDIC), and emits every line where a `FIELD_PATTERNS` field meets a literal, or a
`TARGET_VALUES` value appears (text **or** EBCDIC `X'..'` hex). It over-collects on purpose.

Do this:
1. Ensure `gather_candidates.py` exists in the workspace (it is included with this skill; if you
   only have this text, **create the file** with the exact contents in the code block below).
2. Run it with the CONFIG, e.g. (Windows PowerShell / any shell with Python 3):
   ```
   python gather_candidates.py --src "<SOURCE FOLDER>" --out candidates.csv ^
       --fields "GMAB,??GMAB" --targets "" ^
       --exclude-exts ".md,.json,.log" --name-starts "" --ccsid cp037
   ```
   Map each CONFIG field to the matching `--flag`. It prints `scanned N files; M candidates`.
3. Open `candidates.csv` (columns: `file,line,why,code`). That is your candidate set for STEP 2.
   Report how many candidates were found.

> The script is the deterministic engine — it is what makes this work on millions of lines.
> If `EXTRA_EXCLUDE` rules are easy to express as a path/extension filter, pass them as flags;
> otherwise apply them in STEP 2.

<details><summary><code>gather_candidates.py</code> — full source (create this file if it is not present)</summary>

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 1 of the find-hardcodes skill: gather candidate lines (recall-first, deterministic).
Pure standard library. Judgment happens afterwards (STEP 2). Over-collecting is fine."""
import os, re, csv, sys, argparse, fnmatch

TARGET_VALUES   = []                    # e.g. ["HAAA","HBCB","HSBC"]; empty = ANY
FIELD_PATTERNS  = ["GMAB", "??GMAB"]    # ? = one char, * = many; [] / ["ANY"] = any field
INCLUDE_GLOBS   = ["*"]
EXCLUDE_GLOBS   = []
EXCLUDE_EXTS    = []
NAME_STARTS_WITH= []
EBCDIC_CODEC    = "cp037"

IDENT = "A-Za-z0-9_@#$"
EBCDIC = {'A':'C1','B':'C2','C':'C3','D':'C4','E':'C5','F':'C6','G':'C7','H':'C8','I':'C9',
 'J':'D1','K':'D2','L':'D3','M':'D4','N':'D5','O':'D6','P':'D7','Q':'D8','R':'D9',
 'S':'E2','T':'E3','U':'E4','V':'E5','W':'E6','X':'E7','Y':'E8','Z':'E9',
 '0':'F0','1':'F1','2':'F2','3':'F3','4':'F4','5':'F5','6':'F6','7':'F7','8':'F8','9':'F9'}

COMMENT = re.compile(r"(?i)^[0-9 ]*[HFDICOPJ][*/]")   # fixed-form comment, any prefix width
INLINE  = ("//", "*>", "--")
STRLIT  = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
HEXLIT  = re.compile(r"[Xx]'([0-9A-Fa-f ]+)'")


def field_regex(pats):
    if not pats or pats == ["ANY"]:
        return None
    def one(p):
        out = []
        for c in p:
            if c == "?": out.append("[" + IDENT + "]")
            elif c == "*": out.append("[" + IDENT + "]*")
            else: out.append(re.escape(c))
        return "".join(out)
    alt = "|".join(one(p) for p in pats)
    return re.compile(r"(?<![" + IDENT + r"])(?:" + alt + r")(?![" + IDENT + r"])", re.I)


def to_hex(v):
    try: return "".join(EBCDIC[c] for c in v.upper())
    except KeyError: return None


def decode(path):
    with open(path, "rb") as f:
        data = f.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if data.count(0x40) > data.count(0x20):
        try: return data.decode(EBCDIC_CODEC, errors="replace")
        except Exception: pass
    return data.decode("latin-1")


def unescape(lit):
    q = lit[0]
    return lit[1:-1].replace(q + q, q)


_CTRL = dict.fromkeys([c for c in range(0x20) if c != 0x09] + [0x7f], None)
def clean(s):
    return s.translate(_CTRL)


def in_scope(path, root):
    rel = os.path.relpath(path, root).replace("\\", "/")
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    if EXCLUDE_EXTS and ext in EXCLUDE_EXTS:
        return False
    if NAME_STARTS_WITH:
        if not any(c.startswith(tuple(NAME_STARTS_WITH)) for c in rel.split("/")):
            return False
    if INCLUDE_GLOBS and not any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(name, g)
                                 for g in INCLUDE_GLOBS):
        return False
    if any(fnmatch.fnmatch(rel, g) for g in EXCLUDE_GLOBS):
        return False
    return True


def main():
    global EXCLUDE_EXTS, NAME_STARTS_WITH, INCLUDE_GLOBS, EXCLUDE_GLOBS, EBCDIC_CODEC
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="candidates.csv")
    ap.add_argument("--targets", default=",".join(TARGET_VALUES))
    ap.add_argument("--fields", default=",".join(FIELD_PATTERNS))
    ap.add_argument("--include", default=",".join(INCLUDE_GLOBS))
    ap.add_argument("--exclude", default=",".join(EXCLUDE_GLOBS))
    ap.add_argument("--exclude-exts", default=",".join(EXCLUDE_EXTS))
    ap.add_argument("--name-starts", default=",".join(NAME_STARTS_WITH))
    ap.add_argument("--ccsid", default=EBCDIC_CODEC)
    a = ap.parse_args()

    targets = [t.strip().upper() for t in a.targets.split(",") if t.strip()]
    fields = [f.strip() for f in a.fields.split(",") if f.strip()]
    INCLUDE_GLOBS = [g.strip() for g in a.include.split(",") if g.strip()] or ["*"]
    EXCLUDE_GLOBS = [g.strip() for g in a.exclude.split(",") if g.strip()]
    EXCLUDE_EXTS = [e.strip().lower() for e in a.exclude_exts.split(",") if e.strip()]
    NAME_STARTS_WITH = [n.strip() for n in a.name_starts.split(",") if n.strip()]
    EBCDIC_CODEC = a.ccsid

    frx = field_regex(fields)
    tset = set(targets)
    thex = set(filter(None, (to_hex(v) for v in targets)))

    rows = []
    n_files = 0
    for root, _d, files in os.walk(a.src):
        for fn in files:
            p = os.path.join(root, fn)
            if not in_scope(p, a.src):
                continue
            try:
                text = decode(p)
            except Exception as ex:
                sys.stderr.write("SKIP %s: %s\n" % (p, ex))
                continue
            if "\x00" in text:
                continue
            n_files += 1
            rel = os.path.relpath(p, a.src).replace("\\", "/")
            for i, raw in enumerate(text.split("\n"), 1):
                if COMMENT.match(raw):
                    continue
                code = raw
                for tok in INLINE:
                    j = code.find(tok)
                    if j >= 0:
                        code = code[:j]
                has_field = bool(frx and frx.search(code))
                lits = [unescape(m.group(0)) for m in STRLIT.finditer(code)]
                hexs = ["".join(m.group(1).split()).upper() for m in HEXLIT.finditer(code)]
                why = []
                if has_field and (lits or hexs):
                    why.append("field+literal")
                if tset and any(v in tset for v in (s.upper() for s in lits)):
                    why.append("target-value")
                if thex and any(h in thex for h in hexs):
                    why.append("target-hex")
                if frx is None and (lits or hexs):
                    why.append("any-literal")
                if why:
                    rows.append([rel, i, ";".join(why), clean(raw.rstrip())[:300]])

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "line", "why", "code"])
        w.writerows(rows)
    sys.stderr.write("scanned %d files; %d candidate lines -> %s\n" % (n_files, len(rows), a.out))


if __name__ == "__main__":
    main()
```

</details>

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

### Notes
- **Encoding / hex:** the script handles UTF-8 and EBCDIC, and matches the EBCDIC-hex form of
  target values (uppercase Latin letters are identical across EBCDIC code pages, so CCSID 937
  vs cp037 makes no difference for the hex check).
- **Accuracy:** every result is a candidate for human review. Spot-check HIGH, review MEDIUM/LOW.
