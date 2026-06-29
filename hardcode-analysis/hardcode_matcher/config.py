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

# === EBCDIC CCSID: 037 (US / default) or others. Python codec name. ===
# 037 -> 'cp037'. 1388 (host GBK) has no built-in Python codec; needs a custom map.
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
CONTEXT_LINES = 2

# Optional path to a JSON file with extra, user-supplied detection patterns.
# Set at run time via --patterns, or leave None to use only the built-in anchors A/B.
CUSTOM_PATTERNS_PATH = None
