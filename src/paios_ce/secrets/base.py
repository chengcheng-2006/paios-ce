"""SecretRef abstract interface (secretref architecture).

Invariants enforced by design:
  INVARIANT-1  No secret value in any config file.
  INVARIANT-2  No secret value in logs, audit events, error messages, or
               stack traces. Redacted representations only.
  INVARIANT-3  No secret value passed to an agent that does not need it.
  INVARIANT-5  No secret hash / fingerprint / prefix in public reports,
               public config, or audit events.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import abc
from typing import Optional


class SecretReferenceUnresolved(Exception):
    """Raised when a SecretRef cannot be resolved.

    The message contains only the backend id and reference label, never the
    secret value, never a hash of the value, never a prefix of the value.
    """


class SecretRedactionError(Exception):
    """Raised if a redaction attempt could leak information about a secret.

    Only thrown when a backend is asked for a redaction that would derive from
    the value (which is forbidden); backends are expected to use stable labels
    that do not derive from the value, so this is a safety net.
    """


class SecretValue:
    """Short-lived, in-process secret container with an explicit clear().

    The value is a plain Python str. Workers MUST call clear() when the value
    is no longer needed and at latest at task boundary.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("SecretValue requires a str value")
        self._value = value

    def value(self) -> str:
        return self._value

    def clear(self) -> None:
        self._value = ""

    def redact(self) -> str:
        """Redacted representation that never derives from the value."""
        return "***"

    def __len__(self) -> int:
        return 0

    def __repr__(self) -> str:
        return "<SecretValue redacted>"

    def __str__(self) -> str:
        return "<SecretValue redacted>"


class SecretRef(abc.ABC):
    """Abstract indirection between a config field and a secret value.

    Backends are replaceable; the interface is stable. Every backend must
    satisfy the frozen invariants above.
    """

    backend_id: str = "abstract"

    def __init__(self, ref_id: str) -> None:
        """ref_id is a stable non-secret label used by redact().

        It MUST NOT derive from the secret value (INVARIANT-5).
        """
        if not ref_id or not isinstance(ref_id, str):
            raise ValueError("ref_id must be a non-empty string")
        self._ref_id = ref_id

    @abc.abstractmethod
    def exists(self) -> bool:
        """True if the backend can resolve the reference without returning it."""

    @abc.abstractmethod
    def resolve(self) -> SecretValue:
        """Resolve the secret value into memory for the calling principal.

        MUST NOT log the value. MUST NOT cache beyond the call boundary.
        """

    def redact(self) -> str:
        """Redacted representation safe for logs and audit events.

        Format: "<backend_id>:<stable_label>". The label MUST NOT derive from
        the value. Never returns the value, a prefix, a hash, or a length.
        """
        return f"{self.backend_id}:{self._ref_id}"

    def validate_reference(self) -> bool:
        """Validate the reference shape (NOT the value)."""
        return bool(self._ref_id)

    def rotate_metadata_optional(self) -> Optional[dict]:
        """Optional rotation metadata; MUST NOT include value or value hash."""
        return None

    def __repr__(self) -> str:
        return f"<SecretRef {self.redact()}>"
