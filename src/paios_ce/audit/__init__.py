"""Redacted audit logging (Phase 2 ADR-015 + REDACTION_AND_ERROR_POLICY).

Structured JSONL audit events with mandatory redaction. Secret values, raw
tokens, cookies, authorization headers, raw audio, full private paths, and
Owner identity detail are structurally forbidden from every event.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .logger import RedactedAuditLogger
from .redact import (
    RedactionNotGuaranteedError,
    redaction_guaranteed,
    redact_mapping,
    redact_text,
    redact_value,
    safe_exception,
)

__all__ = [
    "RedactedAuditLogger",
    "RedactionNotGuaranteedError",
    "redaction_guaranteed",
    "redact_mapping",
    "redact_text",
    "redact_value",
    "safe_exception",
]
