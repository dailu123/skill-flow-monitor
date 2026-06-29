# -*- coding: utf-8 -*-
"""
Extensible custom-pattern engine.

The two core anchors (A = value match, B = field reference) are hardcoded for correctness.
This module layers ADDITIONAL, user-supplied detectors on top, so that patterns discovered
later from experience (a routing helper call, an alternate encoding, a new prefix idiom)
can be added WITHOUT editing code -- just a JSON file.

Determinism is preserved: an LLM may AUTHOR a pattern (the regex + metadata), but matching
is done deterministically by re.  See ../patterns/custom_patterns.example.json and the
skill SKILL_hardcode-analysis.md for how to add one.

Pattern JSON schema (one object per pattern):
  {
    "name":        "routing_helper_call",         # required, unique
    "description": "GMAB passed to chkGrpMbr()",   # required, human note
    "regex":       "(?i)chkGrpMbr\\(\\s*'(?P<value>H[A-Z]{3})'",  # required
    "anchor":      "B",            # "A" or "B"  (default "B")
    "match_form":  "ASCII",        # "ASCII" or "HEX"  (default "ASCII")
    "confidence":  "AUTO",         # "HIGH" | "MEDIUM" | "AUTO"  (AUTO = by field adjacency)
    "lang":        "any"           # optional report-only label
  }

Conventions for the regex:
  - Capture the detected value in a named group (?P<value>...). If absent, the whole
    match (group 0) is used as the value.
  - The engine runs each regex on COMMENT-STRIPPED code (strings kept), so matches never
    land in comments. It runs per physical line, so design single-line regexes.
"""
import json
import re

ALLOWED_ANCHORS = ("A", "B")
ALLOWED_FORMS = ("ASCII", "HEX")
ALLOWED_CONF = ("HIGH", "MEDIUM", "AUTO")


class Pattern(object):
    __slots__ = ("name", "description", "regex", "anchor", "match_form",
                 "confidence", "lang")

    def __init__(self, name, description, regex, anchor, match_form,
                 confidence, lang):
        self.name = name
        self.description = description
        self.regex = regex            # compiled
        self.anchor = anchor
        self.match_form = match_form
        self.confidence = confidence
        self.lang = lang


def _validate(obj):
    if not isinstance(obj, dict):
        raise ValueError("pattern must be a JSON object")
    name = obj.get("name")
    rx = obj.get("regex")
    if not name or not isinstance(name, str):
        raise ValueError("pattern.name is required (string)")
    if not rx or not isinstance(rx, str):
        raise ValueError("pattern[%r].regex is required (string)" % name)
    anchor = obj.get("anchor", "B")
    if anchor not in ALLOWED_ANCHORS:
        raise ValueError("pattern[%r].anchor must be one of %s" % (name, ALLOWED_ANCHORS))
    form = obj.get("match_form", "ASCII")
    if form not in ALLOWED_FORMS:
        raise ValueError("pattern[%r].match_form must be one of %s" % (name, ALLOWED_FORMS))
    conf = obj.get("confidence", "AUTO")
    if conf not in ALLOWED_CONF:
        raise ValueError("pattern[%r].confidence must be one of %s" % (name, ALLOWED_CONF))
    try:
        compiled = re.compile(rx)
    except re.error as ex:
        raise ValueError("pattern[%r].regex does not compile: %s" % (name, ex))
    return Pattern(name=name, description=obj.get("description", ""),
                   regex=compiled, anchor=anchor, match_form=form,
                   confidence=conf, lang=obj.get("lang", "any"))


def load_patterns(path):
    """Load and validate custom patterns from a JSON file (a list of pattern objects,
    or {"patterns": [...]}). Returns [] if path is falsy."""
    if not path:
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("patterns", [])
    if not isinstance(data, list):
        raise ValueError("custom patterns file must be a JSON list (or {'patterns': [...]})")
    patterns = []
    seen = set()
    for obj in data:
        p = _validate(obj)
        if p.name in seen:
            raise ValueError("duplicate pattern name: %r" % p.name)
        seen.add(p.name)
        patterns.append(p)
    return patterns


class PatternHit(object):
    __slots__ = ("line", "col", "value", "anchor", "match_form",
                 "confidence", "pattern_name", "lang")

    def __init__(self, line, col, value, anchor, match_form, confidence,
                 pattern_name, lang):
        self.line = line
        self.col = col
        self.value = value
        self.anchor = anchor
        self.match_form = match_form
        self.confidence = confidence      # may be 'AUTO' -> resolved in merge by adjacency
        self.pattern_name = pattern_name
        self.lang = lang


def apply_patterns(code_lines, patterns, lang="any"):
    """Run every pattern against comment-stripped code_lines (1 physical line at a time).
    Returns a list of PatternHit. col is the 1-based column of the captured value."""
    hits = []
    for p in patterns:
        for li, line in enumerate(code_lines, start=1):
            if not line:
                continue
            for m in p.regex.finditer(line):
                if "value" in (m.groupdict() or {}) and m.group("value") is not None:
                    value = m.group("value")
                    col = m.start("value") + 1
                else:
                    value = m.group(0)
                    col = m.start(0) + 1
                hits.append(PatternHit(li, col, value, p.anchor, p.match_form,
                                       p.confidence, p.name, lang))
    return hits
