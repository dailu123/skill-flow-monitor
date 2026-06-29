# -*- coding: utf-8 -*-
"""
GMAB matcher coordinator.

Usage (Windows / any platform, pure stdlib):
    python -m hardcode_matcher.run --src <source root> --out <out dir> \
        --fields GRPMBR,GRPMBRALT --ccsid cp037 --patterns custom_patterns.json

Flow: walk source -> literal_extractor -> field_matcher (adjacency) -> value_matcher (A)
      -> patterns (custom) -> merge_dedup (A U B U patterns, HSBC downgrade, confidence)
      -> report.
No LLM is used for recall. An LLM may optionally classify MEDIUM rows afterwards
(separate step, not in this script).
"""
import argparse
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from hardcode_matcher import (config, literal_extractor, value_matcher,
                                  field_matcher, patterns as patmod,
                                  merge_dedup, report)
else:
    from . import (config, literal_extractor, value_matcher, field_matcher,
                   patterns as patmod, merge_dedup, report)


def process_file(path, field_names, ccsid, custom_patterns=None):
    text, enc = literal_extractor.decode_file(path, ccsid)
    member = os.path.basename(path)
    lines = text.split("\n")
    lits = literal_extractor.extract_from_text(text, path, member)
    lang = literal_extractor.guess_lang(text)
    adj, line_adjacent = field_matcher.annotate_file(lines, lits, field_names)

    def ctx_fn(lit, line=None, _lines=lines):
        ln = line if line is not None else lit.line
        lo = max(0, ln - 1 - config.CONTEXT_LINES)
        hi = min(len(_lines), ln + config.CONTEXT_LINES)
        return "\n".join(s.rstrip() for s in _lines[lo:hi])

    vhits = value_matcher.match_values(lits, codec=ccsid)

    pat_hits = None
    if custom_patterns:
        code_lines = field_matcher.strip_comments(lines)
        pat_hits = patmod.apply_patterns(code_lines, custom_patterns, lang)

    hits = merge_dedup.make_hits(vhits, lits, adj, ctx_fn,
                                 pattern_hits=pat_hits,
                                 line_adjacent=line_adjacent,
                                 member=member, lang=lang)
    return hits, enc


def main(argv=None):
    ap = argparse.ArgumentParser(description="GMAB hardcode matcher")
    ap.add_argument("--src", required=True, help="source root directory")
    ap.add_argument("--out", default="gmab_out", help="output directory")
    ap.add_argument("--fields", default=",".join(config.FIELD_NAMES),
                    help="real group member column name(s), comma-separated")
    ap.add_argument("--ccsid", default=config.EBCDIC_CODEC,
                    help="EBCDIC codec (default cp037)")
    ap.add_argument("--patterns", default=config.CUSTOM_PATTERNS_PATH,
                    help="optional JSON file of custom detection patterns")
    ap.add_argument("--exts", default="",
                    help="optional: only scan these extensions (comma-separated, with dot); empty = all")
    args = ap.parse_args(argv)

    field_names = [f.strip() for f in args.fields.split(",") if f.strip()]
    exts = None
    if args.exts.strip():
        exts = set(e.strip().lower() for e in args.exts.split(","))

    custom_patterns = patmod.load_patterns(args.patterns) if args.patterns else []
    if custom_patterns:
        print("loaded {0} custom pattern(s): {1}".format(
            len(custom_patterns), ", ".join(p.name for p in custom_patterns)))

    all_hits = []
    n_files = 0
    for root, _d, files in os.walk(args.src):
        for fn in files:
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            p = os.path.join(root, fn)
            try:
                hits, _enc = process_file(p, field_names, args.ccsid, custom_patterns)
            except Exception as ex:
                sys.stderr.write("SKIP {0}: {1}\n".format(p, ex))
                continue
            n_files += 1
            all_hits.extend(hits)

    hits_csv, summary_md = report.write_all(all_hits, args.out)
    print("files scanned : {0}".format(n_files))
    print("hits           : {0}".format(len(all_hits)))
    print("hits csv       : {0}".format(hits_csv))
    print("summary        : {0}".format(summary_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
