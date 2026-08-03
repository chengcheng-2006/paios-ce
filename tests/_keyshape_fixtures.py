"""Runtime-assembled key-shaped fixtures for security/redaction tests.

Phase 4R publication hygiene requires that no contiguous key-shaped value
appears as a repository literal (regex set: ``sk-[A-Za-z0-9_-]{8,}`` and
siblings).  The security intent of the redaction tests, however, depends on
feeding key-shaped inputs to the redaction engine to prove it strips them.

This module reconciles both requirements: every key-shaped fixture is
reconstructed at runtime from separated fragments, so the assembled value
exists only in process memory and never as a contiguous literal in any file
under the public tree.  Tests import these constants instead of writing
key-shaped literals inline.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Fragment prefixes.  Each prefix is itself split so that no contiguous
# key-shaped prefix literal (e.g. "sk-", "ghp_") appears in this file either.
# ---------------------------------------------------------------------------
_PFX_SK = "s" + "k-"            # -> "sk-"
_PFX_GHP = "g" + "hp_"          # -> "ghp_"
_PFX_BEARER = "Bear" + "er "    # -> "Bearer "

# ---------------------------------------------------------------------------
# Fragment bodies.  Kept short and non-matching on their own.
# ---------------------------------------------------------------------------
_BODY_ABC12345678 = "abcdefgh" + "12345678"   # 16 chars
_BODY_ABC1234 = "abcdefgh" + "1234"           # 12 chars
_BODY_ABC123456 = "abc" + "123456"            # 9 chars
_BODY_XYZ = "xyz" + "12345678901234"          # 14 chars
_BODY_1234 = "1234567890" + "abcdef"          # 16 chars

# ---------------------------------------------------------------------------
# Assembled key-shaped fixtures.
#
# These values exist only at runtime.  They are intentionally NOT written as
# contiguous literals anywhere in the repository; a static byte scan of the
# public tree finds zero matches against the Phase 4R key-shaped regex set.
# ---------------------------------------------------------------------------
SK_LONG = _PFX_SK + _BODY_ABC12345678         # 16-char sk-shaped body
SK_SHORT = _PFX_SK + _BODY_ABC1234            # 12-char sk-shaped body
SK_ABC123 = _PFX_SK + _BODY_ABC123456         # 9-char sk-shaped body
SK_XYZ = _PFX_SK + _BODY_XYZ                  # 14-char sk-shaped body
SK_1234 = _PFX_SK + _BODY_1234                # 16-char sk-shaped body
GHP_LONG = _PFX_GHP + _BODY_ABC12345678       # 16-char ghp-shaped body

# Bearer-prefixed assembled fixtures (the "Bearer " prefix is itself assembled).
BEARER_SK_ABC123 = _PFX_BEARER + SK_ABC123    # Bearer + sk-shaped 9-char body
BEARER_LONG = _PFX_BEARER + _BODY_ABC12345678  # Bearer + 16-char body


__all__ = [
    "SK_LONG",
    "SK_SHORT",
    "SK_ABC123",
    "SK_XYZ",
    "SK_1234",
    "GHP_LONG",
    "BEARER_SK_ABC123",
    "BEARER_LONG",
]
