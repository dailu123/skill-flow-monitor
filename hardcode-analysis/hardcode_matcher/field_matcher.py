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


# ---------- operator-level binding (precision: literal must bind to the GMAB field) ----------
# A literal is a GMAB hardcode only when it and a GMAB field are the two operands of the SAME
# comparison or assignment -- not merely in the same statement/clause. So between the GMAB
# field token and the literal there may be ONLY "binding glue" (spaces, a relational/assignment
# operator, %SUBST parens/colons/digits, an X/x hex marker). A '+' (concatenation), another
# field, a comma or another quote is a barrier. Examples:
#   IF L1GMAB = 'HBCB'                          -> ' = ' between          -> bound (HIGH)
#   MOVE 'HSBC' K7GMAB                          -> spaces between         -> bound (HIGH)
#   %SUBST(L1GMAB:1:2) = 'HB'                   -> ':1:2) = ' between      -> bound (HIGH)
#   IF (L1STUS='1') AND (L1GMAB<>W3GMAB)        -> '1' clause has no GMAB  -> NOT bound
#   EVAL s2acno = %trim(s2gmab) + '-' + ...     -> '+' between s2gmab,'-'  -> NOT bound
_CONNECTOR = re.compile(r"\b(?:AND|OR)\b", re.IGNORECASE)
_BTOKEN = re.compile(r"[A-Za-z%@#$][A-Za-z0-9%@#$_.]*|<=|>=|<>|[-=<>+*/,();:]|'|\"|\d+")
# fixed-form traditional comparison/assignment word operators allowed as binding glue
_RELOP_WORDS = {"EQ", "NE", "NEQ", "LT", "GT", "LE", "GE", "COMP",
                "IFEQ", "IFNE", "IFGT", "IFLT", "IFGE", "IFLE",
                "DOWEQ", "DOWNE", "DOUEQ", "WHENEQ", "CABEQ", "ANDEQ", "OREQ"}


def _between_ok(between):
    """True if the text between a GMAB field token and the literal is only binding glue."""
    between = between.rstrip()
    if between[-1:] in ("'", '"'):          # the literal's own opening quote (pattern hits
        between = between[:-1].rstrip()      # report the value column, inside the quotes)
    if between[-1:] in ("X", "x"):          # hex literal marker just before the quote
        between = between[:-1]
    for tok in _BTOKEN.findall(between):
        if tok in ("=", "<", ">", "<=", ">=", "<>", "(", ")", ":") or tok.isdigit():
            continue
        if tok.upper() in _RELOP_WORDS:
            continue
        return False                         # '+' '-' '*' '/' ',' quote, or another identifier
    return True


def _clause_span(code_line, idx):
    last = 0
    clauses = []
    for m in _CONNECTOR.finditer(code_line):
        clauses.append((last, m.start()))
        last = m.end()
    clauses.append((last, len(code_line)))
    for s, e in clauses:
        if s <= idx < e:
            return s, e
    return 0, len(code_line)


def _literal_end(s, start):
    """Index of the closing quote of the literal opening at `start` (handles '' escape).
    If `start` is not a quote (a pattern hit points inside the literal), return start."""
    if start >= len(s) or s[start] not in ("'", '"'):
        return start
    q = s[start]
    j = start + 1
    while j < len(s):
        if s[j] == q:
            if j + 1 < len(s) and s[j + 1] == q:
                j += 2
                continue
            return j
        j += 1
    return len(s) - 1


def clause_bound(code_line, col, field_re):
    """True if the literal whose opening quote is at 1-based `col` is an operand of a
    comparison/assignment whose other operand contains a GMAB field token."""
    if not code_line:
        return False
    idx = col - 1
    if idx >= len(code_line):
        return False
    cs, ce = _clause_span(code_line, idx)
    clause = code_line[cs:ce]
    lit_start = idx - cs
    lit_end = _literal_end(clause, lit_start)
    for m in field_re.finditer(clause):
        fs, fe = m.start(), m.end()
        if fe <= lit_start:                  # field before the literal
            between = clause[fe:lit_start]
        elif fs >= lit_end:                  # field after the literal
            between = clause[lit_end + 1:fs]
        else:
            continue
        if _between_ok(between):
            return True
    return False


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
