# -*- coding: utf-8 -*-
"""
Anchor B: field-reference matching (constraint 4) + field-adjacency for confidence
(constraint 6) + HSBC downgrade (constraint 5).

- field_adjacent(lit): does the literal's logical statement reference the group member
  field (real column name)?
- DSPPGMREF only reaches object level; field-level cross-reference must come from a
  source scan, i.e. this module.
"""
import re
from . import config


# ---------- comment stripping (keep strings, so field-name tokens stay searchable) ----------
def strip_comments(lines):
    """Return code-only lines (comments blanked, string contents kept), same length as
    input. Reuses the same comment/string rules as literal_extractor for consistency."""
    out = []
    in_block = False
    in_string = False
    q = ""
    for raw in lines:
        if not in_string and not in_block and _is_fixed_comment(raw):
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
    return out


def _is_fixed_comment(line):
    col = config.FIXED_COMMENT_COL
    if len(line) < col:
        return False
    if line[col - 1] not in ("*", "/"):
        return False
    for ch in line[:5]:
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


# ---------- logical statement segmentation (SQL block to ; / free continuation / fixed per line) ----------
def segment_statements(code_lines):
    """Assign a stmt_id to each line (0-based). Rules (by content, not file name):
    - EXEC SQL ... ;  -> the whole block is one statement (so a multi-line WHERE/SET keeps
      GRPMBR and the value in the same statement).
    - free/SQL continuation: a line ending in + / - / , continues into the next line.
    - everything else (fixed-form RPG C-spec, single-line free statement): one stmt/line.
    - blank line: a boundary.
    """
    ids = [0] * len(code_lines)
    sid = 0
    in_sql = False
    for i, raw in enumerate(code_lines):
        ids[i] = sid
        s = raw.strip()
        up = s.upper()
        if in_sql:
            if ";" in s:
                in_sql = False
                sid += 1
            continue
        if s == "":
            sid += 1
            continue
        if "EXEC SQL" in up and ";" not in s:
            in_sql = True
            continue
        if s.endswith(("+", "-", ",")):
            continue
        sid += 1
    return ids


# ---------- main entry (per file) ----------
def annotate_file(lines, literals, field_names=None):
    """Mark field_adjacent for each literal of this file.
    Returns (adj_map, line_adjacent):
      adj_map[id(lit)] = bool
      line_adjacent[i] = bool for 0-based line i (used for custom-pattern hits)."""
    field_names = field_names or config.FIELD_NAMES
    field_re = field_regex(field_names)
    code_lines = strip_comments(lines)
    stmt_ids = segment_statements(code_lines)

    # Which statement ids reference the field.
    field_stmts = set()
    for i, cl in enumerate(code_lines):
        if cl and has_field(cl, field_re):
            field_stmts.add(stmt_ids[i])

    line_adjacent = [sid in field_stmts for sid in stmt_ids]

    adj = {}
    for lit in literals:
        idx = lit.line - 1
        adj[id(lit)] = line_adjacent[idx] if 0 <= idx < len(line_adjacent) else False
    return adj, line_adjacent
