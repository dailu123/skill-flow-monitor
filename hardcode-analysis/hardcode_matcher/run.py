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
import time


def log(msg):
    """Progress/diagnostics go to stderr (so stdout stays clean for the summary)."""
    sys.stderr.write(time.strftime("%H:%M:%S ") + msg + "\n")
    sys.stderr.flush()


def _fmt_secs(s):
    s = int(s)
    if s < 60:
        return "{0}s".format(s)
    if s < 3600:
        return "{0}m{1:02d}s".format(s // 60, s % 60)
    return "{0}h{1:02d}m".format(s // 3600, (s % 3600) // 60)

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
    prefix = literal_extractor.detect_seq_prefix(lines)
    lits = literal_extractor.extract_from_text(text, path, member)
    lang = literal_extractor.guess_lang(text)
    adj, bound_fn = field_matcher.annotate_file(lines, lits, field_names, prefix)

    def ctx_fn(lit, line=None, _lines=lines):
        ln = line if line is not None else lit.line
        lo = max(0, ln - 1 - config.CONTEXT_LINES)
        hi = min(len(_lines), ln + config.CONTEXT_LINES)
        return "\n".join(s.rstrip() for s in _lines[lo:hi])

    vhits = value_matcher.match_values(lits, codec=ccsid)

    pat_hits = None
    if custom_patterns:
        code_lines = field_matcher.strip_comments(lines, prefix)
        pat_hits = patmod.apply_patterns(code_lines, custom_patterns, lang)

    hits = merge_dedup.make_hits(vhits, lits, adj, ctx_fn,
                                 pattern_hits=pat_hits,
                                 bound_fn=bound_fn,
                                 member=member, lang=lang)
    return hits, enc, len(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="GMAB hardcode matcher")
    ap.add_argument("--src", required=True, help="source root directory")
    ap.add_argument("--out", default="gmab_out", help="output directory")
    ap.add_argument("--fields", default=",".join(config.FIELD_NAMES),
                    help="group member column name(s), comma-separated. Wildcards: "
                         "'?'=one char, '*'=many. HUB uses a 2-char variable prefix, "
                         "so '??GMAB'.")
    ap.add_argument("--ccsid", default=config.EBCDIC_CODEC,
                    help="EBCDIC codec (default cp037)")
    ap.add_argument("--patterns", default=config.CUSTOM_PATTERNS_PATH,
                    help="optional JSON file of custom detection patterns")
    ap.add_argument("--exts", default="",
                    help="optional: only scan these extensions (comma-separated, with dot); empty = all")
    ap.add_argument("--progress-secs", type=float, default=2.0,
                    help="min seconds between progress lines (0 = off)")
    args = ap.parse_args(argv)

    field_names = [f.strip() for f in args.fields.split(",") if f.strip()]
    exts = None
    if args.exts.strip():
        exts = set(e.strip().lower() for e in args.exts.split(","))

    custom_patterns = patmod.load_patterns(args.patterns) if args.patterns else []
    if custom_patterns:
        log("loaded {0} custom pattern(s): {1}".format(
            len(custom_patterns), ", ".join(p.name for p in custom_patterns)))

    # 1) enumerate files first, so we can show counts / percent / ETA
    log("enumerating files under {0} ...".format(args.src))
    all_files = []
    for root, _d, files in os.walk(args.src):
        for fn in files:
            if exts is not None and os.path.splitext(fn)[1].lower() not in exts:
                continue
            all_files.append(os.path.join(root, fn))
    total = len(all_files)
    log("found {0} files; scanning (fields={1}, ccsid={2})".format(
        total, ",".join(field_names), args.ccsid))

    # 2) scan with throttled progress
    all_hits = []
    n_files = 0
    n_lines = 0
    n_skip = 0
    t0 = time.time()
    last = t0
    every = args.progress_secs
    for p in all_files:
        try:
            hits, _enc, nlines = process_file(p, field_names, args.ccsid, custom_patterns)
        except Exception as ex:
            n_skip += 1
            log("SKIP {0}: {1}".format(p, ex))
            continue
        n_files += 1
        n_lines += nlines
        all_hits.extend(hits)
        now = time.time()
        if every > 0 and (now - last >= every or n_files == total):
            el = now - t0
            rate = n_files / el if el > 0 else 0
            eta = (total - n_files) / rate if rate > 0 else 0
            log("[{0:5.1f}%] files {1}/{2}  lines {3:,}  hits {4}  {5:.0f} f/s  "
                "elapsed {6}  ETA {7}  | {8}".format(
                    100.0 * n_files / total if total else 100.0,
                    n_files, total, n_lines, len(all_hits), rate,
                    _fmt_secs(el), _fmt_secs(eta), os.path.basename(p)))
            last = now

    log("writing report ...")
    hits_csv, summary_md = report.write_all(all_hits, args.out)
    log("done in {0}".format(_fmt_secs(time.time() - t0)))
    print("files scanned : {0} ({1} skipped)".format(n_files, n_skip))
    print("lines scanned : {0:,}".format(n_lines))
    print("hits           : {0}".format(len(all_hits)))
    print("hits csv       : {0}".format(hits_csv))
    print("summary        : {0}".format(summary_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
