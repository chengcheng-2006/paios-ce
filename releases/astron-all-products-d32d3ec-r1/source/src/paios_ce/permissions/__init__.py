"""Permission / Risk engine (permission and risk model).

Deny-by-default, capability allowlist, filesystem/network/process scopes,
HIGH-risk confirmation, CRITICAL/admin/shell hard blocks, idempotency and
replay detection.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .engine import (
    AuthorizationReplayRecord,
    Decision,
    PermissionEngine,
    PermissionResult,
    RiskEngine,
    RuleMatch,
    ScopeGuard,
)
from .identity import AuthorizationIdentity, CanonicalizationError, PrincipalContext
from .policy import (
    ActionClass,
    ActionRiskPolicy,
    PolicyDecision,
)

__all__ = [
    "ActionClass",
    "AuthorizationIdentity",
    "AuthorizationReplayRecord",
    "ActionRiskPolicy",
    "CanonicalizationError",
    "Decision",
    "PermissionEngine",
    "PermissionResult",
    "PolicyDecision",
    "PrincipalContext",
    "RiskEngine",
    "RuleMatch",
    "ScopeGuard",
]
