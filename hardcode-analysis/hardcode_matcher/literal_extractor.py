# -*- coding: utf-8 -*-
"""
Constraint 1: extract string literals lexically FIRST, then compare. Never grep raw lines.

Design (confirmed: encoding is mixed; do NOT dispatch lexer by file name):
- Sniff EBCDIC vs ASCII per file. Try strict UTF-8 first (real EBCDIC almost always
  fails strict UTF-8); only then fall back to EBCDIC (config.EBCDIC_CODEC) or latin-1.
- One tolerant lexer works for every language: single- (and double-) quote delimited,
  with a doubled delimiter '' as the in-string escape.
- Comment handling in parallel: fixed-form column-7 '*', free '//', COBOL '*>',
  SQL '--', CL '/* */'.
- Continuation: if a line ends still inside a string, join with the next line
  (GMAB values are only 4 chars and rarely split; this is a safety net).
- Column number = 1-based physical column of the opening quote (alignment preserved
  after decoding).
"""
import os
from . import config


class Literal(object):
    __slots__ = ("path", "member", "line", "col", "value", "raw",
                 "is_hex", "hex_digits", "lang")

    def __init__(self, path, member, line, col, value, raw,
                 is_hex, hex_digits, lang):
        self.path = path
        self.member = member
        self.line = line          # 1-based start line
        self.col = col            # 1-based physical column of the opening quote
        self.value = value        # unescaped content (ASCII text literal)
        self.raw = raw            # original text including quotes
        self.is_hex = is_hex      # X'....' form
        self.hex_digits = hex_digits  # uppercase, no spaces (only when is_hex)
        self.lang = lang

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


# ---------- decoding ----------
def _looks_ebcdic(data):
    """Heuristic, used only when strict UTF-8 failed and we must choose between
    EBCDIC and latin-1: EBCDIC space is 0x40 ('@'), letters fall in 0xC1-0xE9,
    digits in 0xF0-0xF9."""
    if not data:
        return False
    n = len(data)
    c40 = data.count(0x40)                       # EBCDIC space
    c20 = data.count(0x20)                       # ASCII space
    letters = sum(1 for b in data
                  if 0xC1 <= b <= 0xC9 or 0xD1 <= b <= 0xD9 or 0xE2 <= b <= 0xE9)
    digits = sum(1 for b in data if 0xF0 <= b <= 0xF9)
    if c40 > c20 and (letters + digits) > n * 0.20:
        return True
    return False


def decode_file(path, ccsid_codec=None):
    """Return (text, encoding_used). Preserve column alignment: no width change, no strip.
    Strategy for mixed encodings: strict UTF-8 first (source with CJK comments decodes
    here, real EBCDIC fails here); on failure decide EBCDIC vs latin-1 heuristically."""
    ccsid_codec = ccsid_codec or config.EBCDIC_CODEC
    with open(path, "rb") as f:
        data = f.read()
    # 1) Strict UTF-8 first: handles source with CJK comments; EBCDIC usually fails here.
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    # 2) Strict decode failed -> high bytes present. Decide EBCDIC vs latin-1.
    if _looks_ebcdic(data):
        return data.decode(ccsid_codec, errors="replace"), "EBCDIC:" + ccsid_codec
    return data.decode("latin-1"), "latin-1"


# ---------- language guess (report column only; NOT used to dispatch the lexer) ----------
def guess_lang(text):
    t = text.upper()
    if "EXEC SQL" in t:
        return "SQLRPGLE"
    if ("\nPGM" in "\n" + t or " PGM " in t or "MONMSG" in t) and "/*" in t:
        return "CL"
    if "IDENTIFICATION DIVISION" in t or "PROCEDURE DIVISION" in t or "PIC " in t:
        return "COBOL"
    if "**FREE" in t or "DCL-" in t or "//" in t:
        return "RPGLE"
    return "RPG"   # fixed-form fallback


# ---------- sequence-number prefix (SEU seq 6 + date 6 = 12 chars) ----------
def detect_seq_prefix(lines):
    """IBM i source exported with the SEU sequence number + change date keeps a 12-char
    numeric prefix on every record (e.g. '202900000000D...'). That shifts the fixed-form
    RPG columns right by 12 (comment '*' lands in physical column 19, not 7), so it must be
    detected and accounted for. Returns the prefix width (0 or 12).
    Override with config.SEQ_PREFIX_WIDTH (int) to force a value."""
    if getattr(config, "SEQ_PREFIX_WIDTH", None) is not None:
        return config.SEQ_PREFIX_WIDTH
    import re
    pat = re.compile(r"^\d{12}")
    sampled = 0
    hits = 0
    for ln in lines:
        if not ln.strip():
            continue
        sampled += 1
        if pat.match(ln):
            hits += 1
        if sampled >= 200:
            break
    if sampled >= 5 and hits >= sampled * 0.6:
        return 12
    return 0


# ---------- comment detection ----------
def _is_fixed_comment_line(line, prefix=0):
    """Fixed-form comment: form-type column ('*' or '/' in column 7 of the source data),
    with the 5-char sequence area before it blank/digit. `prefix` accounts for the 12-char
    SEU seq+date prefix so the marker is checked at its real (shifted) column."""
    col = prefix + config.FIXED_COMMENT_COL      # column 7 of the source data
    if len(line) < col:
        return False
    if line[col - 1] not in ("*", "/"):
        return False
    for ch in line[prefix:prefix + 5]:           # source-data columns 1-5
        if not (ch == " " or ch.isdigit()):
            return False
    return True


# ---------- literal scanning ----------
def extract_from_text(text, path, member, lang=None):
    """Scan a whole member's text and yield a list of Literal objects."""
    if lang is None:
        lang = guess_lang(text)
    lines = text.split("\n")
    prefix = detect_seq_prefix(lines)
    out = []

    in_block_comment = False     # CL /* */ across lines
    in_string = False
    str_quote = ""
    str_is_hex = False
    str_start_line = 0
    str_start_col = 0
    str_chars = []               # unescaped content
    str_raw = []                 # original text including quotes

    for li, raw_line in enumerate(lines, start=1):
        # Full-line fixed-form comment, but only when not in the middle of a string.
        if not in_string and not in_block_comment and _is_fixed_comment_line(raw_line, prefix):
            continue

        i = 0
        n = len(raw_line)
        while i < n:
            ch = raw_line[i]

            if in_block_comment:
                if raw_line[i:i + 2] == config.BLOCK_COMMENT_CLOSE:
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_string:
                str_raw.append(ch)
                if ch == str_quote:
                    # A doubled delimiter is an escaped quote.
                    if i + 1 < n and raw_line[i + 1] == str_quote:
                        str_chars.append(ch)
                        str_raw.append(str_quote)
                        i += 2
                        continue
                    # End of string.
                    value = "".join(str_chars)
                    raw = "".join(str_raw)
                    hexd = ""
                    if str_is_hex:
                        hexd = "".join(value.split()).upper()
                    out.append(Literal(path, member, str_start_line,
                                       str_start_col, value, raw,
                                       str_is_hex, hexd, lang))
                    in_string = False
                    i += 1
                    continue
                else:
                    str_chars.append(ch)
                    i += 1
                    continue

            # not in_string, not in_block_comment
            if raw_line[i:i + 2] == config.BLOCK_COMMENT_OPEN:   # CL block start
                in_block_comment = True
                i += 2
                continue
            if raw_line[i:i + 2] in config.INLINE_COMMENT_TOKENS:  # // *> -- => rest of line
                break
            if ch in config.QUOTE_CHARS:                         # string start
                in_string = True
                str_quote = ch
                str_start_line = li
                str_start_col = i + 1  # 1-based physical column
                # hex literal: the immediately preceding char is X/x
                str_is_hex = (i >= 1 and raw_line[i - 1] in ("X", "x"))
                str_chars = []
                str_raw = [ch]
                i += 1
                continue
            i += 1

        # End of line while still inside a string: in fixed/free RPG, COBOL, CL and SQL a
        # quoted literal does not span physical lines without an explicit continuation, and
        # GMAB values are only 4 chars. So CLOSE the string at end of line rather than
        # merging into the next one -- this prevents a stray apostrophe (e.g. in an
        # unstripped "Customer's DCN" comment) from swallowing the rest of the file.
        if in_string:
            in_string = False
            str_is_hex = False
            str_chars = []
            str_raw = []

    return out


def extract_file(path, ccsid_codec=None):
    text, enc = decode_file(path, ccsid_codec)
    member = os.path.basename(path)
    return extract_from_text(text, path, member), enc
