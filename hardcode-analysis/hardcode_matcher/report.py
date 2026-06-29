# -*- coding: utf-8 -*-
"""
Output: a hit detail CSV + a summary. Columns follow the task specification.
"""
import csv
import os
from collections import defaultdict
from . import config

HIT_COLUMNS = ["program", "member", "line", "col", "matched_value",
               "match_form", "anchor", "statement", "field_adjacent",
               "confidence", "lang", "pattern"]


_CTRL = dict.fromkeys(
    [c for c in range(0x20) if c not in (0x09,)] + [0x7f], None)


def _clean(v):
    """Strip control chars (a stray binary file scanned as source shouldn't break CSV)."""
    if isinstance(v, str):
        return v.translate(_CTRL)
    return v


def write_hits_csv(hits, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HIT_COLUMNS)
        w.writeheader()
        for h in sorted(hits, key=lambda x: (x.member, x.line, x.col)):
            w.writerow({k: _clean(v) for k, v in h.as_row().items()})


def build_summary(hits):
    per_value = defaultdict(lambda: {"total": 0, "ASCII": 0, "HEX": 0,
                                     "HIGH": 0, "MEDIUM": 0})
    out_of_list = []   # anchor-B / pattern hits whose value is not in the 15-value set
    for h in hits:
        if h.in_gmab_set:
            d = per_value[h.matched_value]
            d["total"] += 1
            d[h.match_form] = d.get(h.match_form, 0) + 1
            d[h.confidence] = d.get(h.confidence, 0) + 1
        else:
            out_of_list.append(h)
    return per_value, out_of_list


def write_summary(hits, path):
    per_value, out_of_list = build_summary(hits)
    lines = []
    lines.append("# GMAB hit summary\n")
    lines.append("## Hits per value (in-set 15 values only)\n")
    lines.append("| value | total | ASCII | HEX | HIGH | MEDIUM |")
    lines.append("|---|---|---|---|---|---|")
    for v in config.GMAB_VALUES:
        d = per_value.get(v, {"total": 0, "ASCII": 0, "HEX": 0,
                              "HIGH": 0, "MEDIUM": 0})
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            v, d["total"], d["ASCII"], d["HEX"], d["HIGH"], d["MEDIUM"]))
    lines.append("")
    lines.append("## Out-of-list candidates from anchor B / custom patterns (manual review)\n")
    if not out_of_list:
        lines.append("_(none)_")
    else:
        lines.append("| member | line | col | candidate | pattern | statement |")
        lines.append("|---|---|---|---|---|---|")
        for h in sorted(out_of_list, key=lambda x: (x.member, x.line)):
            stmt = h.statement.replace("\n", " / ").replace("|", "\\|")
            lines.append("| {0} | {1} | {2} | `{3}` | {4} | {5} |".format(
                h.member, h.line, h.col, h.matched_value,
                h.pattern_name or "", stmt[:200]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_all(hits, out_dir):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    hits_csv = os.path.join(out_dir, "gmab_hits.csv")
    summary_md = os.path.join(out_dir, "gmab_summary.md")
    write_hits_csv(hits, hits_csv)
    write_summary(hits, summary_md)
    return hits_csv, summary_md
