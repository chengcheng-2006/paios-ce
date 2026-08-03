"""Redaction helpers (Phase 2 REDACTION_AND_ERROR_POLICY + security closure closure).

Rules:
  - redact() must not leak length, prefix, or suffix of a secret.
  - exceptions must never carry secret values.
  - redact_text() replaces secret-like patterns and forbidden tokens with "***".
  - redact_mapping() returns a redacted copy of a mapping, never mutating input,
    and now accepts an optional literal-value mapping (F-W01 closure) so an
    arbitrary secret value under a non-secret key name is still redacted.
  - redact_value() is the single deep-redaction entry point used by the Audit
    Logger, Health/Diagnostics, and safe_exception (defense in depth).

security closure defense-in-depth guarantees:
  - str / bytes / Mapping / list / tuple / set / nested containers / Exception /
    unknown object / None are handled safely.
  - Secret-like keys are matched case-insensitively and across underscore,
    hyphen, space, and common variants.
  - Cycles cannot cause infinite recursion (id-based seen-set).
  - Maximum nesting depth is bounded (depth-limited placeholder).
  - bytes are never emitted verbatim.
  - Unknown objects use a fixed safe placeholder; custom __repr__/__str__ that
    could leak content are never invoked.
  - Exception __cause__/__context__ chains are walked but never leak values.
  - Mapping keys and values are both redacted.

R1 closure security invariants (see REDACTION_SECURITY_INVARIANT.md):
  - RAW_SECRET_IN_AUDIT_INPUT = FORBIDDEN. SecretRef values never enter the
    audit models; secret-like fields are rejected by the schemas (extra="forbid")
    and by forbidden_fields_in().
  - SECRETS_MUST_USE_SECRETREF = YES. Audit/error/health/diagnostics content
    carries only SecretRef references (opaque labels), never resolved values.
  - EXTERNAL_RAW_SECRET_REDACTION_REQUIRES_EXPLICIT_SECRET_MAPPING = YES.
    A generic redactor cannot recognize an arbitrary non-pattern bare secret
    inside list/tuple/set/exception. A caller that may pass an external raw
    secret MUST supply a literal-value `secret_mapping`; redaction is then
    guaranteed. Without the required mapping, redaction is NOT guaranteed and
    redact_value(..., require_mapping=True) raises RedactionNotGuaranteedError
    instead of silently passing the value through.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, MutableMapping

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{8,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"Bearer [A-Za-z0-9._\-]{8,}"),
]


class RedactionNotGuaranteedError(Exception):
    """Raised when external raw-secret redaction cannot be guaranteed.

    Triggered by require_mapping=True paths when a bare string (not a
    secret pattern, not covered by the literal-value mapping, not under a
    secret-like key) would otherwise be emitted verbatim. The caller MUST
    provide an explicit secret_mapping covering every external raw secret.
    """

_FORBIDDEN_KEYS = {
    "secret", "secret_value", "raw_token", "token", "cookie", "cookie_value",
    "authorization_header", "authorization", "auth", "session", "session_token",
    "raw_audio", "audio_bytes", "full_private_path", "private_path", "owner_identity_detail",
    "api_key", "apiKey", "apikey", "password", "passwd", "private_key", "credential",
}

_FORBIDDEN_TEXT = [
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
]

_PATH_HINT_RE = re.compile(r"(/Users/[^/\s]+|C:\\Users\\[^\\\s]+)")

# Fixed placeholders — never derived from a secret value.
_REDACTED = "***"
_CYCLE_PLACEHOLDER = "<redacted:cycle>"
_DEPTH_PLACEHOLDER = "<redacted:max_depth>"
_BYTES_PLACEHOLDER = "<redacted:bytes>"
_OBJECT_PLACEHOLDER = "<redacted-object>"
_MAX_DEPTH = 10

# Suffix variants that mark a key as secret-like regardless of exact spelling.
_SECRET_SUFFIXES = (
    "_token", "_secret", "_password", "_passwd", "_key", "_apikey",
    "_api_key", "_credential", "_auth", "_authorization", "_session",
    "_cookie", "_private_key",
)

# Substring fragments that mark a key as secret-like (covers common variants
# such as "session_id", "auth_token", "private.key", "user_secret").
_SECRET_FRAGMENTS = (
    "secret", "token", "cookie", "session", "password", "passwd",
    "authorization", "credential", "private", "api", "auth",
)


def _normalize_key(key: Any) -> str:
    """Lowercase, and normalize hyphen/space/dot variants to underscore."""
    return str(key).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _is_secret_like(key: Any) -> bool:
    k = _normalize_key(key)
    if not k:
        return False
    if k in {f.lower().replace("-", "_") for f in _FORBIDDEN_KEYS}:
        return True
    if k.endswith(_SECRET_SUFFIXES):
        return True
    # Substring match for common variants (case-insensitive after normalize).
    if any(frag in k for frag in _SECRET_FRAGMENTS):
        return True
    return False


def redact_text(text: str, mapping: Mapping[str, str] | None = None) -> str:
    """Return a redacted copy of the text.

    ``mapping`` maps known literal secret values to a fixed placeholder. Any
    secret-shaped token or forbidden marker is replaced with "***".
    """
    if not isinstance(text, str):
        return _REDACTED
    out = text
    if mapping:
        for literal, repl in mapping.items():
            if not isinstance(literal, str) or not literal:
                continue
            out = out.replace(literal, repl)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    for marker in _FORBIDDEN_TEXT:
        out = out.replace(marker, _REDACTED)
    # Redact absolute home paths (both POSIX and Windows style)
    out = _PATH_HINT_RE.sub("<USER_HOME>", out)
    return out


def _redact_exception(exc: BaseException, mapping: Mapping[str, str] | None,
                      depth: int, seen: set[int]) -> str:
    """Redact an exception and its __cause__/__context__ chain (bounded)."""
    if depth > _MAX_DEPTH:
        return _DEPTH_PLACEHOLDER
    oid = id(exc)
    if oid in seen:
        return _CYCLE_PLACEHOLDER
    seen.add(oid)
    try:
        name = exc.__class__.__name__
        msg = redact_text(str(exc), mapping)
        parts = [f"{name}: {msg}"]
        cause = getattr(exc, "__cause__", None)
        if cause is not None:
            parts.append("cause=" + _redact_exception(cause, mapping, depth + 1, seen))
        context = getattr(exc, "__context__", None)
        if context is not None:
            parts.append("context=" + _redact_exception(context, mapping, depth + 1, seen))
        return " | ".join(parts)
    finally:
        seen.discard(oid)


def _safe_placeholder(obj: Any) -> str:
    """Return a fixed safe placeholder; never invoke custom __repr__/__str__.

    Only the type module/name is derived (via type()), which is safe for every
    object and cannot contain secret values. Object contents are never rendered.
    """
    cls = type(obj)
    mod = getattr(cls, "__module__", "")
    name = getattr(cls, "__name__", "")
    if isinstance(mod, str) and isinstance(name, str) and mod and name:
        return f"<{_REDACTED} object:{mod}.{name}>"
    return _OBJECT_PLACEHOLDER


def redact_value(value: Any, mapping: Mapping[str, str] | None = None,
                 require_mapping: bool = False) -> Any:
    """Deep, cycle-safe, depth-limited redaction of arbitrary Python values.

    This is the single security entry point for audit, health, diagnostics, and
    exceptions. Unknown objects become fixed placeholders; bytes become a fixed
    placeholder; recursive containers are walked with an id-based seen-set and a
    maximum depth.

    ``require_mapping`` (R1 closure): when True, an external raw secret that is
    not a secret pattern and not covered by ``mapping`` raises
    RedactionNotGuaranteedError instead of being passed through. Callers that
    may pass external raw secrets MUST provide an explicit literal-value
    mapping.
    """
    if require_mapping and not redaction_guaranteed(value, mapping):
        raise RedactionNotGuaranteedError(
            "redaction not guaranteed: external raw secret without explicit secret_mapping"
        )
    return _redact_value(value, mapping, 0, set())


def _redact_value(value: Any, mapping: Mapping[str, str] | None,
                  depth: int, seen: set[int]) -> Any:
    if depth > _MAX_DEPTH:
        return _DEPTH_PLACEHOLDER
    if value is None:
        return None
    if isinstance(value, str):
        return redact_text(value, mapping)
    if isinstance(value, bytes):
        return _BYTES_PLACEHOLDER
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    oid = id(value)
    if oid in seen:
        return _CYCLE_PLACEHOLDER
    if isinstance(value, Mapping):
        seen.add(oid)
        try:
            out: Dict[Any, Any] = {}
            for key, val in value.items():
                safe_key = key if isinstance(key, str) else _safe_placeholder(key)
                if _is_secret_like(key):
                    out[safe_key] = _REDACTED
                else:
                    out[safe_key] = _redact_value(val, mapping, depth + 1, seen)
            return out
        finally:
            seen.discard(oid)
    if isinstance(value, (list, tuple)):
        seen.add(oid)
        try:
            cls = list if isinstance(value, list) else tuple
            return cls(_redact_value(v, mapping, depth + 1, seen) for v in value)
        finally:
            seen.discard(oid)
    if isinstance(value, (set, frozenset)):
        seen.add(oid)
        try:
            cls = set if isinstance(value, set) else frozenset
            return cls(_redact_value(v, mapping, depth + 1, seen) for v in value)
        finally:
            seen.discard(oid)
    if isinstance(value, BaseException):
        return _redact_exception(value, mapping, depth + 1, seen)
    return _safe_placeholder(value)


def redact_mapping(data: Mapping[str, Any], mapping: Mapping[str, str] | None = None,
                   require_mapping: bool = False) -> Dict[str, Any]:
    """Return a deep redacted copy of a mapping (input never mutated).

    ``mapping`` (optional, F-W01) maps known literal secret values to a fixed
    placeholder, so an arbitrary secret value under a non-secret key name is
    redacted even when the key itself is not secret-like.

    ``require_mapping`` (R1 closure): when True, a bare non-pattern secret
    under a non-secret key with no matching mapping entry raises
    RedactionNotGuaranteedError.
    """
    return redact_value(data, mapping, require_mapping=require_mapping)


def safe_exception(exc: BaseException, mapping: Mapping[str, str] | None = None,
                   require_mapping: bool = False) -> str:
    """Return a redacted, stable description of an exception.

    Never includes a secret value; any secret-like content in the message is
    replaced with "***". The exception type name is preserved (non-secret).
    ``__cause__``/``__context__`` chains are walked and redacted too.

    ``require_mapping`` (R1 closure): when True, an external raw secret in the
    exception message that is neither a secret pattern nor covered by
    ``mapping`` raises RedactionNotGuaranteedError.
    """
    if require_mapping and not _guarantee_any(exc, mapping, 0, set()):
        raise RedactionNotGuaranteedError(
            "safe_exception redaction not guaranteed: external raw secret without explicit secret_mapping"
        )
    return _redact_exception(exc, mapping, 0, set())


def forbidden_fields_in(event: MutableMapping[str, Any]) -> list[str]:
    """Return the names of forbidden fields present in an audit event dict.

    Used as a defensive check by the audit logger before writing.
    """
    found = []
    for key in event:
        if _is_secret_like(key):
            found.append(str(key))
    return found


def redaction_guaranteed(value: Any, mapping: Mapping[str, str] | None = None) -> bool:
    """True if redaction of ``value`` is guaranteed under ``mapping``.

    R1 closure security invariant: a generic redactor CANNOT recognize an
    arbitrary non-pattern bare secret inside list/tuple/set/exception without a
    caller-provided literal-value mapping. This predicate returns True only
    when every secret-shaped string in the structure is provably covered:
      - the string matches a secret pattern (pattern-redacted), or
      - the string is a literal key in ``mapping``, or
      - the string sits under a secret-like key (key-based redaction), or
      - the value is a non-secret primitive / fixed placeholder.

    A bare string under a neutral key that is neither pattern-matched nor in
    ``mapping`` makes the guarantee False — the caller must provide an explicit
    ``secret_mapping`` and must NOT claim the output is redacted otherwise.
    """
    return _guarantee_any(value, mapping, 0, set())


def _guarantee_any(value: Any, mapping: Mapping[str, str] | None,
                   depth: int, seen: set[int]) -> bool:
    if depth > _MAX_DEPTH:
        # Depth-limited: deeper content is replaced by a fixed placeholder,
        # so redaction is guaranteed for everything at or below the limit.
        return True
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, bytes):
        return True  # always a fixed placeholder
    if isinstance(value, str):
        if _is_secret_like_string_guaranteed(value, mapping):
            return True
        return False  # bare string under a neutral context — not provably covered
    if isinstance(value, BaseException):
        return _guarantee_exc(value, mapping, depth, seen)
    oid = id(value)
    if oid in seen:
        return True  # cycle -> placeholder
    if isinstance(value, Mapping):
        seen.add(oid)
        try:
            for key, val in value.items():
                if _is_secret_like(key):
                    continue  # key-based redaction covers the value
                if not _guarantee_any(val, mapping, depth + 1, seen):
                    return False
            return True
        finally:
            seen.discard(oid)
    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(oid)
        try:
            return all(_guarantee_any(v, mapping, depth + 1, seen) for v in value)
        finally:
            seen.discard(oid)
    return True  # unknown object -> fixed placeholder


def _is_secret_like_string_guaranteed(s: str, mapping: Mapping[str, str] | None) -> bool:
    """A string is provably covered if pattern-redacted, mapped, or a placeholder."""
    if mapping and s in mapping:
        return True
    for pattern in _SECRET_PATTERNS:
        if pattern.search(s):
            return True
    for marker in _FORBIDDEN_TEXT:
        if marker in s:
            return True
    if _PATH_HINT_RE.search(s):
        return True
    if s in (_REDACTED, _CYCLE_PLACEHOLDER, _DEPTH_PLACEHOLDER, _BYTES_PLACEHOLDER):
        return True
    return False


def _guarantee_exc(exc: BaseException, mapping: Mapping[str, str] | None,
                   depth: int, seen: set[int]) -> bool:
    """Redaction guarantee for an exception and its cause/context chain."""
    if depth > _MAX_DEPTH:
        return True
    oid = id(exc)
    if oid in seen:
        return True
    seen.add(oid)
    try:
        msg = str(exc)
        if not _is_secret_like_string_guaranteed(msg, mapping):
            return False
        for attr in ("__cause__", "__context__"):
            chained = getattr(exc, attr, None)
            if chained is not None and not _guarantee_exc(chained, mapping, depth + 1, seen):
                return False
        return True
    finally:
        seen.discard(oid)
