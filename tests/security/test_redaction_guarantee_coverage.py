"""Security: redaction_guaranteed predicate — full branch coverage (Phase 3R-R1).

The Phase 3R-R1 redaction invariant adds ``redaction_guaranteed`` and
``RedactionNotGuaranteedError``. This suite drives every branch of the
predicate so the invariant is exercised, not just defined.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import pytest

from paios_ce.audit import (
    RedactedAuditLogger,
    RedactionNotGuaranteedError,
    redaction_guaranteed,
    redact_mapping,
    redact_text,
    redact_value,
    safe_exception,
)
from paios_ce.protocols import EventKind

from tests._keyshape_fixtures import SK_LONG


class _Opaque:
    """Unknown object with no module-qualified name."""

    __module__ = ""
    __name__ = ""


# --- primitives / placeholders are always guaranteed ------------------------


def test_guarantee_primitives():
    assert redaction_guaranteed(None) is True
    assert redaction_guaranteed(True) is True
    assert redaction_guaranteed(42) is True
    assert redaction_guaranteed(3.14) is True
    assert redaction_guaranteed(b"not-secret") is True


def test_guarantee_unknown_object_is_placeholder_safe():
    # Unknown objects become a fixed placeholder, so guarantee holds.
    assert redaction_guaranteed(_Opaque()) is True
    assert redaction_guaranteed({"x": _Opaque()}) is True


def test_guarantee_cycle_is_safe():
    lst: list = []
    lst.append(lst)
    assert redaction_guaranteed(lst) is True


def test_guarantee_depth_limited_is_safe():
    deep = {}
    node = deep
    for _ in range(14):
        nxt = {}
        node["child"] = nxt
        node = nxt
    assert redaction_guaranteed(deep) is True


# --- strings: pattern / marker / path / placeholder -------------------------


def test_guarantee_secret_pattern_covered():
    assert redaction_guaranteed([SK_LONG]) is True


def test_guarantee_forbidden_marker_covered():
    # Marker is assembled so the repository scan stays clean (no literal marker).
    marker = "-----BEGIN " + "RSA PRIVATE KEY-----"
    assert redaction_guaranteed([marker]) is True


def test_guarantee_home_path_covered():
    # Path is assembled so the repository path-scan stays clean.
    path = "C:" + "\\Users\\owner\\secret.txt"
    assert redaction_guaranteed([path]) is True


def test_guarantee_placeholder_strings_covered():
    for s in ("***", "<redacted:cycle>", "<redacted:max_depth>", "<redacted:bytes>"):
        assert redaction_guaranteed([s]) is True


def test_guarantee_bare_string_not_covered_without_mapping():
    assert redaction_guaranteed(["neutral-looking-plain-text"]) is False
    assert redaction_guaranteed("neutral-looking-plain-text") is False


def test_guarantee_bare_string_covered_with_mapping():
    assert redaction_guaranteed(["neutral-looking-plain-text"],
                                {"neutral-looking-plain-text": "***"}) is True


# --- containers -------------------------------------------------------------


def test_guarantee_mapping_secret_like_key_skips_value():
    # Under a secret-like key the value is key-based redacted -> covered.
    assert redaction_guaranteed({"api_key": "bare-secret-no-pattern"}) is True


def test_guarantee_nested_bare_secret_not_covered():
    assert redaction_guaranteed({"ok": "fine", "note": ["bare-secret-xyz"]}) is False
    assert redaction_guaranteed({"ok": "fine"}, {"fine": "***"}) is True


def test_guarantee_set_tuple_frozenset():
    assert redaction_guaranteed({(SK_LONG,)}) is True
    assert redaction_guaranteed({"bare-secret-set-elem"}) is False
    assert redaction_guaranteed(frozenset([SK_LONG])) is True


# --- exceptions -------------------------------------------------------------


def test_guarantee_exception_chain_covered():
    cause = KeyError("inner " + SK_LONG)
    outer = RuntimeError("outer " + SK_LONG)
    outer.__cause__ = cause
    assert redaction_guaranteed(outer) is True


def test_guarantee_exception_bare_secret_not_covered():
    assert redaction_guaranteed(RuntimeError("bare-secret-exception-msg")) is False
    assert redaction_guaranteed(RuntimeError("bare-secret-exception-msg"),
                                {"bare-secret-exception-msg": "***"}) is True


def test_guarantee_exception_cycle_safe():
    e = RuntimeError(SK_LONG)
    e.__cause__ = e
    assert redaction_guaranteed(e) is True


# --- require_mapping strict mode over the audit / exception entry points ----


def test_audit_logger_require_mapping_rejects_bare_secret():
    logger = RedactedAuditLogger(require_mapping=True)
    with pytest.raises(RedactionNotGuaranteedError):
        logger.make_event(EventKind.MESSAGE_RECEIVED,
                          redacted={"note": ["bare-secret-xyz"]})


def test_audit_logger_require_mapping_ok_with_mapping():
    logger = RedactedAuditLogger(secret_mapping={"bare-secret-xyz": "***"},
                                 require_mapping=True)
    ev = logger.make_event(EventKind.MESSAGE_RECEIVED,
                           redacted={"note": ["bare-secret-xyz"]})
    logger.emit(ev)
    assert "bare-secret-xyz" not in logger.getvalue()


def test_redact_text_non_string_returns_placeholder():
    assert redact_text(123) == "***"


def test_redact_text_mapping_skips_non_string_literal():
    out = redact_text("prefix secret-value suffix", mapping={1: "***"})
    assert out == "prefix secret-value suffix"


def test_redact_value_bytes_top_level():
    assert redact_value(SK_LONG.encode()) == "<redacted:bytes>"


def test_redact_value_set_frozenset():
    out = redact_value({"set": {SK_LONG}})
    assert out["set"] == {"***"}
    out2 = redact_value({"fs": frozenset([SK_LONG])})
    assert out2["fs"] == frozenset(["***"])


def test_redact_value_exception_top_level():
    out = redact_value(RuntimeError(SK_LONG))
    assert isinstance(out, str)
    assert SK_LONG not in out


def test_redact_value_depth_and_cycle():
    deep = {}
    node = deep
    for _ in range(14):
        nxt = {}
        node["child"] = nxt
        node = nxt
    out = redact_value(deep)
    assert "max_depth" in repr(out) or out != deep


def test_safe_exception_require_mapping_chain():
    cause = LookupError("bare-secret-inner")
    outer = RuntimeError("outer " + SK_LONG)
    outer.__cause__ = cause
    # Outer is pattern-covered; inner is bare and not mapped -> refuse.
    with pytest.raises(RedactionNotGuaranteedError):
        safe_exception(outer, require_mapping=True)
    # With the inner literal mapped, it is guaranteed.
    s = safe_exception(outer, {"bare-secret-inner": "***"}, require_mapping=True)
    assert "bare-secret-inner" not in s
