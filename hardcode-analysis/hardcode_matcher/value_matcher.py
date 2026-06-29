# -*- coding: utf-8 -*-
"""
Anchor A: value matching (constraint 2) + EBCDIC hex form (constraint 3).
Runs on the literals from literal_extractor: exact match (case-sensitive, full 4 chars,
no substring fuzzing).
"""
from . import config


def build_hex_table(values=None, codec=None):
    """Encode each of the 15 values to its EBCDIC hex string.
    Returns {hex_upper: value}. Example: HBCB -> 'C8C2C3C2' (cp037)."""
    values = values or config.GMAB_VALUES
    codec = codec or config.EBCDIC_CODEC
    table = {}
    for v in values:
        hexs = v.encode(codec).hex().upper()
        table[hexs] = v
    return table


class ValueHit(object):
    __slots__ = ("lit", "matched_value", "match_form")

    def __init__(self, lit, matched_value, match_form):
        self.lit = lit
        self.matched_value = matched_value
        self.match_form = match_form  # 'ASCII' / 'HEX'


def match_values(literals, values=None, codec=None):
    """Return a list of ValueHit (anchor A)."""
    value_set = set(values or config.GMAB_VALUES)
    hex_table = build_hex_table(values, codec)
    hits = []
    for lit in literals:
        if lit.is_hex:
            if lit.hex_digits in hex_table:   # already uppercase, no spaces
                hits.append(ValueHit(lit, hex_table[lit.hex_digits], "HEX"))
        else:
            if lit.value in value_set:        # exact, full, case-sensitive
                hits.append(ValueHit(lit, lit.value, "ASCII"))
    return hits
