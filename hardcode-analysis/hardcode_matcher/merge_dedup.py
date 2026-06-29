# -*- coding: utf-8 -*-
"""
Constraint 7: union and de-duplicate. Final list = anchor A (incl. hex) U anchor B
U custom-pattern hits. De-dup key = (program, member, line, col, matched_value).
Recall ("never miss") is the top priority for parity.
Constraint 5: HSBC kept only when field_adjacent.
Constraint 6: HIGH = field-adjacent, MEDIUM = not field-adjacent.
"""
import os
from . import config


class Hit(object):
    __slots__ = ("program", "member", "line", "col", "matched_value",
                 "match_form", "anchor", "statement", "field_adjacent",
                 "confidence", "lang", "in_gmab_set", "pattern_name")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def key(self):
        return (self.program, self.member, self.line, self.col,
                self.matched_value)

    def as_row(self):
        return {
            "program": self.program,
            "member": self.member,
            "line": self.line,
            "col": self.col,
            "matched_value": self.matched_value,
            "match_form": self.match_form,
            "anchor": self.anchor,
            "statement": self.statement,
            "field_adjacent": "true" if self.field_adjacent else "false",
            "confidence": self.confidence,
            "lang": self.lang,
            "pattern": self.pattern_name or "",
        }


def _program_of_member(member):
    # member is the source file name; the program object name is usually member minus ext.
    return os.path.splitext(member)[0]


def _resolve_conf(declared, field_adjacent):
    if declared in ("HIGH", "MEDIUM"):
        return declared
    return "HIGH" if field_adjacent else "MEDIUM"   # AUTO


def make_hits(value_hits, literals, adj_map, ctx_fn,
              pattern_hits=None, line_adjacent=None, member=None, lang="any"):
    """
    value_hits:    anchor A (ValueHit list)
    literals:      all literals (for the anchor-B scan)
    adj_map:       field_adjacent per literal (by id(lit))
    ctx_fn:        lit -> statement string (with +/- CONTEXT_LINES of context)
    pattern_hits:  optional list of patterns.PatternHit for this member
    line_adjacent: optional per-line adjacency (0-based) for pattern hits
    member/lang:   used for pattern hits (no Literal to read them from)
    """
    gmab_set = set(config.GMAB_VALUES)
    hits = {}

    # ---- anchor A ----
    for vh in value_hits:
        lit = vh.lit
        fa = adj_map.get(id(lit), False)
        if vh.matched_value == config.HSBC_VALUE and not fa:   # HSBC downgrade
            continue
        h = Hit(program=_program_of_member(lit.member), member=lit.member,
                line=lit.line, col=lit.col, matched_value=vh.matched_value,
                match_form=vh.match_form, anchor="A", statement=ctx_fn(lit),
                field_adjacent=fa, confidence=("HIGH" if fa else "MEDIUM"),
                lang=lit.lang, in_gmab_set=(vh.matched_value in gmab_set),
                pattern_name=None)
        hits[h.key()] = h

    # ---- anchor B: any field-adjacent string literal (incl. out-of-list values) ----
    for lit in literals:
        if lit.is_hex:
            continue   # hex already covered by A
        if not adj_map.get(id(lit), False):
            continue
        val = lit.value
        h = Hit(program=_program_of_member(lit.member), member=lit.member,
                line=lit.line, col=lit.col, matched_value=val,
                match_form="ASCII", anchor="B", statement=ctx_fn(lit),
                field_adjacent=True, confidence="HIGH", lang=lit.lang,
                in_gmab_set=(val in gmab_set), pattern_name=None)
        k = h.key()
        if k in hits:
            existing = hits[k]
            existing.field_adjacent = True
            existing.confidence = "HIGH"
        else:
            hits[k] = h

    # ---- custom-pattern hits ----
    if pattern_hits:
        member = member or (literals[0].member if literals else "")
        prog = _program_of_member(member)
        for ph in pattern_hits:
            fa = False
            if line_adjacent is not None and 0 <= ph.line - 1 < len(line_adjacent):
                fa = line_adjacent[ph.line - 1]
            if ph.value == config.HSBC_VALUE and not fa:   # HSBC downgrade applies too
                continue
            conf = _resolve_conf(ph.confidence, fa)
            h = Hit(program=prog, member=member, line=ph.line, col=ph.col,
                    matched_value=ph.value, match_form=ph.match_form,
                    anchor=ph.anchor, statement=ctx_fn(None, ph.line),
                    field_adjacent=fa, confidence=conf, lang=ph.lang or lang,
                    in_gmab_set=(ph.value in gmab_set),
                    pattern_name=ph.pattern_name)
            k = h.key()
            if k not in hits:
                hits[k] = h
            else:
                # keep richer field_adjacent / record the pattern provenance
                ex = hits[k]
                if fa and not ex.field_adjacent:
                    ex.field_adjacent = True
                    ex.confidence = "HIGH"
                if not ex.pattern_name:
                    ex.pattern_name = ph.pattern_name

    return list(hits.values())
