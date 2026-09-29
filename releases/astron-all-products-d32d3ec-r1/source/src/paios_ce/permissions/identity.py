"""Canonical identities for in-memory authorization replay.

These structures deliberately describe authorization only. They neither record
execution nor provide durable recovery.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from pydantic import BaseModel

from ..secrets import SecretRef, SecretValue


class CanonicalizationError(ValueError):
    """Raised when a request cannot safely receive a stable fingerprint."""


@dataclass(frozen=True)
class PrincipalContext:
    """Trusted runtime-side identity, intentionally separate from ActionRequest."""

    principal_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.principal_id, str) or not self.principal_id.strip():
            raise ValueError("principal_id must be a non-empty string")
        object.__setattr__(self, "principal_id", self.principal_id.strip())


@dataclass(frozen=True)
class AuthorizationIdentity:
    """Identity that a single in-memory authorization replay record binds."""

    idempotency_key: str
    principal_id: str
    request_fingerprint: str
    security_context_fingerprint: str


def canonical_sha256(value: Any) -> str:
    """Return SHA-256 over deterministic, typed, canonical JSON.

    The input is normalized without ``str()``, ``repr()``, Python ``hash()``,
    secret resolution, or arbitrary-object rendering. Unsupported values fail
    closed through :class:`CanonicalizationError`.
    """

    normalized = _normalize(value, set())
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:  # defensive; normalization is typed
        raise CanonicalizationError("canonical JSON serialization failed") from exc
    return hashlib.sha256(encoded).hexdigest()


def authorization_identity(
    request: Any,
    principal: PrincipalContext,
    security_context: Mapping[str, Any],
) -> AuthorizationIdentity:
    """Build the stable identity for a keyed authorization request."""

    key = getattr(request, "idempotency_key", None)
    if not isinstance(key, str) or not key:
        raise CanonicalizationError("idempotency key is absent or invalid")
    request_payload = {
        "format": "astron.authorization-request.v1",
        "trusted_principal_id": principal.principal_id,
        "action": _security_relevant_action(request),
    }
    return AuthorizationIdentity(
        idempotency_key=key,
        principal_id=principal.principal_id,
        request_fingerprint=canonical_sha256(request_payload),
        security_context_fingerprint=canonical_sha256(
            {
                "format": "astron.authorization-security-context.v1",
                "context": dict(security_context),
            }
        ),
    )


def _security_relevant_action(request: Any) -> dict[str, Any]:
    """Return only the ActionRequest values relevant to authorization.

    ``action_id`` is a transport/submission identifier and is handled by the
    separate duplicate-action guard. A top-level ``trace_id`` parameter is
    logging metadata in the current architecture, so it does not make a new
    authorization intent. ``admin_token`` is never rendered or hashed; the
    current permission engine does not inspect its value, so only its presence
    is represented.
    """

    parameters = getattr(request, "parameters", {})
    if not isinstance(parameters, Mapping):
        raise CanonicalizationError("action parameters must be a mapping")
    security_parameters = {
        key: value
        for key, value in parameters.items()
        if key != "trace_id"
    }
    fs_scope = getattr(request, "filesystem_scope", None)
    network_scope = getattr(request, "network_scope", None)
    process_scope = getattr(request, "process_scope", None)
    return {
        "manifest_version": getattr(request, "manifest_version", None),
        "worker_type": getattr(request, "worker_type", None),
        "operation": getattr(request, "operation", None),
        "parameters": security_parameters,
        "required_permissions": sorted(set(getattr(request, "required_permissions", ()) or ())),
        "filesystem_scope": {
            "mode": getattr(fs_scope, "mode", None),
            "paths_class": sorted(set(getattr(fs_scope, "paths_class", ()) or ())),
        },
        "network_scope": {
            "mode": getattr(network_scope, "mode", None),
            "endpoints_class": sorted(set(getattr(network_scope, "endpoints_class", ()) or ())),
        },
        "process_scope": None if process_scope is None else {
            "allowed_executables_class": sorted(
                set(getattr(process_scope, "allowed_executables_class", ()) or ())
            ),
        },
        "timeout": getattr(request, "timeout", None),
        "rollback_supported": getattr(request, "rollback_supported", None),
        "approval_required": getattr(request, "approval_required", None),
        "admin_token_present": getattr(request, "admin_token", None) is not None,
    }


def _normalize(value: Any, seen: set[int]) -> Any:
    """Normalize supported structured values without exposing secret material."""

    if value is None:
        return None
    if isinstance(value, SecretValue):
        raise CanonicalizationError("resolved secret values are not canonicalizable")
    if isinstance(value, SecretRef):
        try:
            safe_reference = value.redact()
        except Exception as exc:  # never fall back to repr/str for a SecretRef
            raise CanonicalizationError("secret reference identity unavailable") from exc
        if not isinstance(safe_reference, str) or not safe_reference:
            raise CanonicalizationError("secret reference identity invalid")
        return {
            "$secret_ref": {
                "backend_id": value.backend_id,
                "reference": safe_reference,
            }
        }
    if isinstance(value, Enum):
        return {"$enum": _normalize(value.value, seen)}
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return {"$number": _normalize_number(Decimal(value))}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("non-finite float is not canonicalizable")
        return {"$number": _normalize_number(Decimal(str(value)))}
    if isinstance(value, Decimal):
        return {"$number": _normalize_number(value)}
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        raise CanonicalizationError("bytes are not canonicalizable")

    identity = id(value)
    if identity in seen:
        raise CanonicalizationError("cyclic values are not canonicalizable")
    if isinstance(value, BaseModel):
        return _normalize_model(value, seen)
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_dataclass(value, seen)
    if isinstance(value, Mapping):
        return _normalize_mapping(value, seen)
    if isinstance(value, (list, tuple)):
        seen.add(identity)
        try:
            return {"$list": [_normalize(item, seen) for item in value]}
        finally:
            seen.remove(identity)
    if isinstance(value, (set, frozenset)):
        seen.add(identity)
        try:
            normalized = [_normalize(item, seen) for item in value]
            return {
                "$set": sorted(
                    normalized,
                    key=lambda item: json.dumps(
                        item, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ),
                )
            }
        finally:
            seen.remove(identity)
    raise CanonicalizationError("unsupported parameter type")


def _normalize_number(value: Decimal) -> str:
    try:
        if not value.is_finite():
            raise CanonicalizationError("non-finite decimal is not canonicalizable")
        if value == 0:
            return "0"
        normalized = value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    except (InvalidOperation, ValueError) as exc:
        raise CanonicalizationError("number normalization failed") from exc


def _normalize_mapping(value: Mapping[Any, Any], seen: set[int]) -> dict[str, Any]:
    identity = id(value)
    seen.add(identity)
    try:
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("mapping keys must be strings")
            normalized[key] = _normalize(item, seen)
        return {"$map": normalized}
    finally:
        seen.remove(identity)


def _normalize_model(value: BaseModel, seen: set[int]) -> dict[str, Any]:
    identity = id(value)
    seen.add(identity)
    try:
        return {
            "$model": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
            "value": _normalize_mapping(value.model_dump(mode="python"), seen),
        }
    finally:
        seen.remove(identity)


def _normalize_dataclass(value: Any, seen: set[int]) -> dict[str, Any]:
    identity = id(value)
    seen.add(identity)
    try:
        payload = {item.name: getattr(value, item.name) for item in fields(value)}
        return {
            "$dataclass": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
            "value": _normalize_mapping(payload, seen),
        }
    finally:
        seen.remove(identity)
