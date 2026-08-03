"""Permission / Risk engine (Phase 2 ADR-007 + ACTION_RISK_TAXONOMY).

Deny-by-default, capability allowlist, filesystem/network/process scopes,
HIGH-risk confirmation, CRITICAL/admin/shell hard blocks, idempotency and
replay detection.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .engine import (
    Decision,
    PermissionEngine,
    PermissionResult,
    RiskEngine,
    RuleMatch,
    ScopeGuard,
)
from .policy import (
    ActionClass,
    ActionRiskPolicy,
    PolicyDecision,
)

__all__ = [
    "ActionClass",
    "ActionRiskPolicy",
    "Decision",
    "PermissionEngine",
    "PermissionResult",
    "PolicyDecision",
    "RiskEngine",
    "RuleMatch",
    "ScopeGuard",
]
