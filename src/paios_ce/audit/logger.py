"""RedactedAuditLogger — JSONL structured audit with mandatory redaction.

Default output is JSONL, one event per line. Every event is validated against
the AuditEvent model (extra="forbid") and checked for forbidden fields before
write. If a forbidden field is present, the event is refused and an
audit_write_failed event is emitted instead (never the offending content).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TextIO

from ..protocols import AuditEvent, EventKind, RiskLevel
from .redact import (
    forbidden_fields_in,
    redact_mapping,
    redact_text,
    redact_value,
)

_MANIFEST_VERSION = "0.1.0"


class RedactedAuditLogger:
    """Writes redacted AuditEvents as JSONL.

    ``stream`` may be any text stream (default: in-memory BytesIO-like StringIO
    for tests) or a file opened by the caller. Never auto-opens production
    logs. Default output stays in memory unless a stream is provided.

    ``secret_mapping`` (F-W01) maps known literal secret values to a fixed
    placeholder, so an external raw secret under a neutral key is redacted.

    ``require_mapping`` (Phase 3R-R1): when True, a bare non-pattern secret in
    the redacted details that is neither pattern-redacted nor covered by
    ``secret_mapping`` raises RedactionNotGuaranteedError instead of being
    silently passed through. Default internal paths (False) do not receive raw
    secrets and do not claim a mapping guarantee.
    """

    def __init__(self, stream: Optional[TextIO] = None, audit_config: Optional[dict] = None,
                 secret_mapping: Optional[Dict[str, str]] = None,
                 require_mapping: bool = False) -> None:
        self._stream = stream if stream is not None else io.StringIO()
        self._cfg = dict(audit_config or {})
        self._secret_mapping = dict(secret_mapping or {})
        self._require_mapping = require_mapping
        self._events: List[AuditEvent] = []

    # -- event construction -------------------------------------------------

    def make_event(
        self,
        event_type: EventKind,
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        risk_level: Optional[RiskLevel] = None,
        actor_type: str = "system",
        component: str = "paios_ce",
        outcome: str = "ok",
        redacted: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        event_id = "evt_" + uuid.uuid4().hex[:12]
        return AuditEvent(
            event_id=event_id,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            trace_id=trace_id,
            task_id=task_id,
            event_type=event_type,
            risk_level=risk_level,
            actor_type=actor_type,
            component=component,
            outcome=outcome,
            redacted_details=redact_mapping(
                redacted or {}, self._secret_mapping,
                require_mapping=self._require_mapping,
            ),
        )

    # -- write path ----------------------------------------------------------

    def emit(self, event: AuditEvent) -> None:
        """Validate, redact, and write one event as a JSONL line."""
        payload = self._to_payload(event)
        forbidden = forbidden_fields_in(payload)
        if forbidden:
            self._emit_audit_write_failed(task_id=event.task_id, trace_id=event.trace_id,
                                          reason="forbidden fields rejected")
            return
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        self._stream.write(line + "\n")
        self._stream.flush()
        self._events.append(event)

    def _to_payload(self, event: AuditEvent) -> Dict[str, Any]:
        data = event.model_dump(exclude_none=True)
        data["manifest_version"] = _MANIFEST_VERSION
        # Defensive redaction at write time: even if redacted_details was
        # mutated after construction, no secret-shaped value reaches the log.
        if isinstance(data.get("redacted_details"), dict):
            data["redacted_details"] = redact_mapping(
                data["redacted_details"], self._secret_mapping,
                require_mapping=self._require_mapping,
            )
        else:
            data["redacted_details"] = redact_value(
                data.get("redacted_details"), self._secret_mapping,
                require_mapping=self._require_mapping,
            )
        return data

    def _emit_audit_write_failed(self, task_id: Optional[str], trace_id: Optional[str], reason: str) -> None:
        ev = AuditEvent(
            event_id="evt_" + uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            trace_id=trace_id,
            task_id=task_id,
            event_type=EventKind.AUDIT_WRITE_FAILED,
            outcome="audit_write_failed",
            redacted_details={"reason": redact_text(reason)},
        )
        self._stream.write(json.dumps(ev.model_dump(exclude_none=True), ensure_ascii=True, sort_keys=True) + "\n")
        self._stream.flush()

    # -- read path ------------------------------------------------------------

    def getvalue(self) -> str:
        return self._stream.getvalue()

    def events(self) -> List[AuditEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
        if hasattr(self._stream, "truncate"):
            self._stream.truncate(0)
            self._stream.seek(0)
