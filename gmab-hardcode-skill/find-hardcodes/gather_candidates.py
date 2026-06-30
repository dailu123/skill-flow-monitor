#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 1 of the find-hardcodes skill: gather candidate lines (recall-first, deterministic).
Pure standard library. Judgment happens afterwards (STEP 2). Over-collecting is fine."""
import os, re, csv, sys, argparse, fnmatch

# ----------------------------------------------------------------------------- CONFIG
# (these get overwritten from CLI args; defaults match the skill's CONFIG block)
TARGET_VALUES   = []                    # e.g. ["HAAA","HBCB","HSBC"]; empty = ANY
FIELD_PATTERNS  = ["GMAB", "??GMAB"]    # ? = one char, * = many; [] / ["ANY"] = any field
INCLUDE_GLOBS   = ["*"]
EXCLUDE_GLOBS   = []
EXCLUDE_EXTS    = []                    # e.g. [".md",".json"]
NAME_STARTS_WITH= []                    # e.g. ["IB","GL"]
EBCDIC_CODEC    = "cp037"

IDENT = "A-Za-z0-9_@#$"
EBCDIC = {'A':'C1','B':'C2','C':'C3','D':'C4','E':'C5','F':'C6','G':'C7','H':'C8','I':'C9',
 'J':'D1','K':'D2','L':'D3','M':'D4','N':'D5','O':'D6','P':'D7','Q':'D8','R':'D9',
 'S':'E2','T':'E3','U':'E4','V':'E5','W':'E6','X':'E7','Y':'E8','Z':'E9',
 '0':'F0','1':'F1','2':'F2','3':'F3','4':'F4','5':'F5','6':'F6','7':'F7','8':'F8','9':'F9'}

# fixed-form comment, any prefix width: digits/spaces + form-type letter + '*' or '/'
COMMENT = re.compile(r"(?i)^[0-9 ]*[HFDICOPJ][*/]")
INLINE  = ("//", "*>", "--")            # free RPGLE / COBOL inline / SQL
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
    if data.count(0x40) > data.count(0x20):     # EBCDIC space dominates -> EBCDIC
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
        comps = rel.split("/")
        if not any(c.startswith(tuple(NAME_STARTS_WITH)) for c in comps):
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
            if "\x00" in text:                      # binary file (e.g. .pyc) -> skip
                continue
            n_files += 1
            rel = os.path.relpath(p, a.src).replace("\\", "/")
            for i, raw in enumerate(text.split("\n"), 1):
                if COMMENT.match(raw):
                    continue
                code = raw
                for tok in INLINE:                     # drop inline-comment tail
                    j = code.find(tok)
                    if j >= 0:
                        # keep it simple: only cut if not obviously inside a quote
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
                if frx is None and (lits or hexs):      # FIELD=ANY -> any literal line
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
