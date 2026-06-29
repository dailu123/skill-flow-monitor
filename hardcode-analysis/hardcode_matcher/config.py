# -*- coding: utf-8 -*-
"""
Configuration for the GMAB hardcode matcher.

Pure Python standard library. Runs on Windows. No shell, no third-party deps.

Edit only this file to fill in parameters:
  - FIELD_NAMES : real column name(s), filled AFTER the precheck (SYSCOLUMNS + DISTINCT).
  - EBCDIC_CODEC: the host CCSID codec, if not 037.
GMAB_VALUES is a CLOSED enumeration. Do not add/remove values without human
confirmation (constraint: never silently widen/narrow the keyword set).
"""

# === Closed enumeration: the 15 GMAB values (4 chars, fixed length, prefix H). Frozen. ===
GMAB_VALUES = [
    "HAAA", "HBBJ", "HBCB", "HBCD", "HBCF",
    "HBCQ", "HBDP", "HBFU", "HBGD", "HBHT",
    "HBHU", "HBMC", "HBSD", "HBSH", "HSBC",
]

# HSBC downgrade: counted ONLY when its literal's statement references the group member field.
HSBC_VALUE = "HSBC"

# === Real column name(s) of the group member field (there may be aliases). ===
# Confirm via the precheck (QSYS2.SYSCOLUMNS + DISTINCT on the real table).
# Case-insensitive, matched on token boundaries (so xxGMAB_FLAG is NOT a false hit).
# Wildcards are supported for variable-prefix names:
#   '?' = exactly one identifier char,  '*' = zero or more.
# In HUB the group member column is named "<2 variable chars>GMAB", so use "??GMAB".
FIELD_NAMES = [
    "??GMAB",   # 2 variable prefix chars + GMAB; add aliases here if SYSCOLUMNS shows any
]

# === EBCDIC CCSID: Python codec name used (a) to decode raw EBCDIC files and (b) to build
# the X'..' hex keyword table. ===
# HUB source is CCSID 937 (Traditional Chinese host). Python has no cp937 codec, but the 15
# GMAB codes are uppercase Latin letters, which are INVARIANT across EBCDIC code pages, so
# cp037 produces the same bytes (HBCB -> X'C8C2C3C2') and the hex check is unaffected.
# Raw-937 source still decodes its SBCS letters correctly under cp037 (only DBCS Chinese,
# which never appears in a GMAB value, would garble). Leave cp037 unless a value contains
# non-invariant characters.
EBCDIC_CODEC = "cp037"

# String delimiters (single quote is universal across RPG/COBOL/CL/SQL;
# COBOL/SQL may also use double quotes).
QUOTE_CHARS = ("'", '"')

# Comment markers (line-level and inline).
FIXED_COMMENT_COL = 7          # column 7 (1-based) '*' or '/' => fixed-form comment line
INLINE_COMMENT_TOKENS = ("//", "*>", "--")  # free RPGLE / COBOL inline / SQL
BLOCK_COMMENT_OPEN = "/*"      # CL block comment
BLOCK_COMMENT_CLOSE = "*/"

# Identifier characters (RPG allows @ # $; qualified names use '.').
IDENT_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_@#$")

# Context lines around a hit (the `statement` column shows +/- this many lines).
# 0 = show only the matched line.
CONTEXT_LINES = 0

# Optional path to a JSON file with extra, user-supplied detection patterns.
# Set at run time via --patterns, or leave None to use only the built-in anchors A/B.
CUSTOM_PATTERNS_PATH = None

# SEU sequence-number + date prefix width. IBM i source exported with seq+date keeps a
# 12-char numeric prefix on every record, which shifts the fixed-form columns. None = auto
# detect per file (lines starting with 12 digits); set an int to force (e.g. 0 or 12).
SEQ_PREFIX_WIDTH = None
