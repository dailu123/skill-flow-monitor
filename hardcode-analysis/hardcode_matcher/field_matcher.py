# -*- coding: utf-8 -*-
"""
Anchor B: field-reference matching (constraint 4) + field binding for confidence
(constraint 6) + HSBC downgrade (constraint 5).

- A literal binds to the group member field only when it shares the SAME comparison/
  assignment CLAUSE as a GMAB field token (split on AND/OR), not merely the same statement.
  This rejects compound-statement coincidences such as
  `IF (L1STUS='1') AND (L1GMAB<>W3GMAB)` (the '1' is bound to L1STUS, not GMAB) and
  field-to-field comparisons, while keeping `IF L1GMAB='HBCB'`, `MOVE 'HSBC' K7GMAB`,
  and `%SUBST(L1GMAB:1:2)='HB'`.
- DSPPGMREF only reaches object level; field-level cross-reference must come from a
  source scan, i.e. this module.
"""
import re
from . import config


# ---------- comment stripping (keep strings, so field-name tokens stay searchable) ----------
def strip_comments(lines, prefix=0):
    """Return code-only lines (comments blanked, string contents kept), same length as
    input. Reuses the same comment/string rules as literal_extractor for consistency.
    `prefix` is the SEU seq+date prefix width (see literal_extractor.detect_seq_prefix)."""
    out = []
    in_block = False
    in_string = False
    q = ""
    for raw in lines:
        if not in_string and not in_block and _is_fixed_comment(raw, prefix):
            out.append("")
            continue
        buf = []
        i = 0
        n = len(raw)
        while i < n:
            ch = raw[i]
            if in_block:
                if raw[i:i + 2] == config.BLOCK_COMMENT_CLOSE:
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            if in_string:
                buf.append(ch)
                if ch == q:
                    if i + 1 < n and raw[i + 1] == q:
                        buf.append(q)
                        i += 2
                        continue
                    in_string = False
                i += 1
                continue
            if raw[i:i + 2] == config.BLOCK_COMMENT_OPEN:
                in_block = True
                i += 2
                continue
            if raw[i:i + 2] in config.INLINE_COMMENT_TOKENS:
                break
            if ch in config.QUOTE_CHARS:
                in_string = True
                q = ch
                buf.append(ch)
                i += 1
                continue
            buf.append(ch)
            i += 1
        out.append("".join(buf))
        in_string = False   # strings do not span physical lines (see literal_extractor)
        q = ""
    return out


def _is_fixed_comment(line, prefix=0):
    col = prefix + config.FIXED_COMMENT_COL
    if len(line) < col:
        return False
    if line[col - 1] not in ("*", "/"):
        return False
    for ch in line[prefix:prefix + 5]:
        if not (ch == " " or ch.isdigit()):
            return False
    return True


# ---------- field token detection ----------
def _field_alt(name, idents_cls):
    """Translate one field-name spec into a regex fragment.
    Wildcards (for variable-prefix column names like the HUB '??GMAB'):
      '?' = exactly one identifier char   -> e.g. '??GMAB' = 2 free chars + GMAB
      '*' = zero or more identifier chars
    Everything else is matched literally (re.escaped)."""
    out = []
    for ch in name:
        if ch == "?":
            out.append("[" + idents_cls + "]")
        elif ch == "*":
            out.append("[" + idents_cls + "]*")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def field_regex(field_names):
    """Token-boundary match (avoids GRPMBR_FLAG / X_GRPMBR false hits) via negative
    lookbehind/lookahead on the identifier char set (fixed width, safe).
    Supports '?'/'*' wildcards so a variable-prefix column name like '??GMAB' works."""
    idents = re.escape("".join(sorted(config.IDENT_CHARS)))
    alt = "|".join(_field_alt(f, idents) for f in field_names)
    pat = "(?<![" + idents + "])(?:" + alt + ")(?![" + idents + "])"
    return re.compile(pat, re.IGNORECASE)


def has_field(text, field_re):
    return field_re.search(text) is not None


# ---------- clause-level binding (precision: literal must bind to the GMAB field) ----------
# A literal counts as a GMAB hardcode only when it sits in the SAME comparison/assignment
# clause as a GMAB field -- not merely the same statement. Splitting on the boolean
# connectors AND/OR isolates each comparison, so:
#   IF L1GMAB = 'HBCB'                         -> '1' clause has GMAB  -> bound (HIGH)
#   MOVE 'HSBC' K7GMAB                          -> one clause has GMAB  -> bound (HIGH)
#   %SUBST(L1GMAB:1:2) = 'HB'                   -> one clause has GMAB  -> bound (HIGH)
#   IF (L1STUS='1') AND (L1GMAB<>W3GMAB)        -> '1' clause = (L1STUS='1'), no GMAB -> NOT bound
#   WHERE GMAB='HBHU' ... AND STATUS='HBSD'     -> 'HBSD' clause has no GMAB -> NOT bound
_CONNECTOR = re.compile(r"\b(?:AND|OR)\b", re.IGNORECASE)


def clause_bound(code_line, col, field_re):
    """True if the literal whose opening quote is at 1-based `col` shares its AND/OR clause
    with a GMAB field token."""
    if not code_line:
        return False
    idx = col - 1
    last = 0
    clauses = []
    for m in _CONNECTOR.finditer(code_line):
        clauses.append((last, m.start()))
        last = m.end()
    clauses.append((last, len(code_line)))
    for s, e in clauses:
        if s <= idx < e:
            return field_re.search(code_line[s:e]) is not None
    return field_re.search(code_line) is not None   # idx on a boundary: fall back to line


# ---------- main entry (per file) ----------
def annotate_file(lines, literals, field_names=None, prefix=0):
    """Mark field_adjacent (clause-bound) for each literal of this file.
    Returns (adj_map, bound_fn):
      adj_map[id(lit)] = bool
      bound_fn(line_1based, col_1based) -> bool   (for custom-pattern hits)."""
    field_names = field_names or config.FIELD_NAMES
    field_re = field_regex(field_names)
    code_lines = strip_comments(lines, prefix)

    def bound_fn(line, col):
        idx = line - 1
        if 0 <= idx < len(code_lines):
            return clause_bound(code_lines[idx], col, field_re)
        return False

    adj = {}
    for lit in literals:
        adj[id(lit)] = bound_fn(lit.line, lit.col)
    return adj, bound_fn
