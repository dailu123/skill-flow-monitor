# -*- coding: utf-8 -*-
"""Small-sample validation: column numbers, '' escape, comment stripping, EBCDIC hex,
HSBC downgrade, and custom patterns.
Run: python -m hardcode_matcher.samples.selftest   (or: python selftest.py)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # hardcode-analysis/
sys.path.insert(0, ROOT)

from hardcode_matcher import literal_extractor as LE
from hardcode_matcher import value_matcher as VM
from hardcode_matcher import patterns as PAT
from hardcode_matcher import run as RUN
from hardcode_matcher import config

EXAMPLE_PATTERNS = os.path.join(ROOT, "patterns", "custom_patterns.example.json")


def show_literals(path):
    text, enc = LE.decode_file(path)
    member = os.path.basename(path)
    lits = LE.extract_from_text(text, path, member)
    print("== literals in {0}  (encoding={1}) ==".format(member, enc))
    for L in lits:
        tag = "HEX" if L.is_hex else "STR"
        print("  L{0:>2} C{1:>2} [{2}] value={3!r}{4}".format(
            L.line, L.col, tag, L.value,
            ("  hex=" + L.hex_digits) if L.is_hex else ""))
    print()


def show_hits(path, custom=None):
    hits, enc = RUN.process_file(path, config.FIELD_NAMES, config.EBCDIC_CODEC, custom)
    print("== HITS in {0} ==".format(os.path.basename(path)))
    print("  {0:<4} {1:<4} {2:<10} {3:<6} {4:<2} {5:<6} {6:<6} {7}".format(
        "line", "col", "value", "form", "A/B", "conf", "fadj", "pattern"))
    for h in sorted(hits, key=lambda x: (x.line, x.col)):
        print("  {0:<4} {1:<4} {2:<10} {3:<6} {4:<2} {5:<6} {6:<6} {7}".format(
            h.line, h.col, h.matched_value, h.match_form, h.anchor,
            h.confidence, str(h.field_adjacent), h.pattern_name or ""))
    print()


def show_hex_table():
    print("== EBCDIC hex keyword table ({0}) ==".format(config.EBCDIC_CODEC))
    for hexs, v in sorted(VM.build_hex_table().items(), key=lambda kv: kv[1]):
        print("  {0} -> X'{1}'".format(v, hexs))
    print()


def ebcdic_roundtrip_test():
    src = ("     C                   IF        GRPMBR = 'HBCB'\n"
           "     C                   IF        GRPMBR = X'C8C2C3C2'\n")
    data = src.encode(config.EBCDIC_CODEC)
    p = os.path.join(HERE, "_ebcdic_tmp.bin")
    with open(p, "wb") as f:
        f.write(data)
    print("== EBCDIC file decode + extract ==")
    show_literals(p)
    show_hits(p)
    os.remove(p)


if __name__ == "__main__":
    show_hex_table()
    custom = PAT.load_patterns(EXAMPLE_PATTERNS)
    print("loaded custom patterns: {0}\n".format([p.name for p in custom]))
    show_literals(os.path.join(HERE, "SAMPLE_RPG_FIXED.rpg"))
    show_hits(os.path.join(HERE, "SAMPLE_RPG_FIXED.rpg"), custom)
    show_literals(os.path.join(HERE, "SAMPLE_MIXED.txt"))
    show_hits(os.path.join(HERE, "SAMPLE_MIXED.txt"), custom)
    ebcdic_roundtrip_test()
