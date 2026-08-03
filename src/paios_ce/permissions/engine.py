"""Permission / Risk engine — deny-by-default authorization for ActionRequests.

Design notes (ADR-007 + WORKER_PERMISSION_MODEL):
  - Every worker starts with zero capabilities.
  - Capabilities are granted explicitly by name (capability allowlist).
  - Filesystem and network scope checks compare requested scope against the
    granted scope.
  - HIGH-risk actions require confirmation (channel_prompt or owner_approval).
  - CRITICAL actions, admin elevation, arbitrary shell, and process execution
    are hard-blocked in the current release candidate.
  - Replay detection: request_id uniqueness. Idempotency: idempotency_key
    may be used to replay safely (returns cached result).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Set

from ..protocols import (
    ActionRequest,
    ConfirmationKind,
    FsScopeMode,
    NetworkScopeMode,
    RiskLevel,
)
from .policy import ActionClass, ActionRiskPolicy, PolicyDecision


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    BLOCKED = "blocked"
    CONFIRMATION_REQUIRED = "confirmation_required"


@dataclass(frozen=True)
class RuleMatch:
    action_class: ActionClass
    risk_level: RiskLevel
    reason: str
    hard_blocked: bool = False
    confirmation_kind: ConfirmationKind = ConfirmationKind.NONE


@dataclass
class PermissionResult:
    decision: Decision
    action_class: Optional[ActionClass]
    risk_level: Optional[RiskLevel]
    reason: str
    hard_blocked: bool = False
    confirmation_kind: ConfirmationKind = ConfirmationKind.NONE
    is_replay: bool = False
    error_code: Optional[str] = None
    execution_attempted: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


class ScopeGuard:
    """Tracks granted filesystem/network/process scopes for a worker."""

    def __init__(
        self,
        fs_read_classes: Iterable[str] = (),
        fs_write_classes: Iterable[str] = (),
        network_loopback: bool = True,
        network_egress_classes: Iterable[str] = (),
        process_classes: Iterable[str] = (),
    ) -> None:
        self.fs_read = set(fs_read_classes)
        self.fs_write = set(fs_write_classes)
        self.network_loopback = network_loopback
        self.network_egress = set(network_egress_classes)
        self.process = set(process_classes)


class RiskEngine:
    """Pure classification layer; maps an ActionRequest to a RuleMatch."""

    def __init__(self, policy: Optional[ActionRiskPolicy] = None) -> None:
        self._policy = policy or ActionRiskPolicy()

    def evaluate(self, request: ActionRequest) -> RuleMatch:
        perms = frozenset(request.required_permissions or [])
        network_mode = (
            request.network_scope.mode.value
            if request.network_scope
            else NetworkScopeMode.NONE.value
        )
        action_class = ActionRiskPolicy.classify(request.operation, perms, network_mode)
        decision = self._policy.lookup(action_class)
        return RuleMatch(
            action_class=decision.action_class,
            risk_level=decision.risk_level,
            reason=decision.reason,
            hard_blocked=decision.hard_blocked,
            confirmation_kind=decision.confirmation_kind,
        )

    def risk_of(self, request: ActionRequest) -> RiskLevel:
        return self.evaluate(request).risk_level


class PermissionEngine:
    """Authorizes ActionRequests under a capability + scope grant."""

    def __init__(
        self,
        capabilities: Iterable[str] = (),
        owner_allowlist: Iterable[str] = (),
        principal_id: str = "principal:example.invalid/user-1",
        scope_guard: Optional[_ScopeGuard] = None,
        high_risk_confirmation_enabled: bool = True,
        policy: Optional[ActionRiskPolicy] = None,
    ) -> None:
        self._capabilities: Set[str] = set(capabilities)
        self._owners: Set[str] = set(owner_allowlist)
        self._principal = principal_id
        self._is_owner = principal_id in self._owners
        self._scope = scope_guard or ScopeGuard()
        self._high_risk_confirmation = high_risk_confirmation_enabled
        self._risk = RiskEngine(policy)
        self._seen_request_ids: Set[str] = set()
        self._seen_action_ids: Set[str] = set()
        self._idempotency_results: Dict[str, PermissionResult] = {}

    # -- capability / principal plumbing -----------------------------------

    def is_owner(self) -> bool:
        return self._is_owner

    def has_capability(self, capability: str) -> bool:
        return capability in self._capabilities

    def _deny(self, reason: str, action_class: Optional[ActionClass] = None,
              risk: Optional[RiskLevel] = None, hard: bool = False,
              confirm: ConfirmationKind = ConfirmationKind.NONE,
              error_code: Optional[str] = None) -> PermissionResult:
        return PermissionResult(Decision.DENY, action_class, risk, reason,
                                hard_blocked=hard, confirmation_kind=confirm,
                                error_code=error_code)

    def _block(self, reason: str, action_class: Optional[ActionClass] = None,
               risk: Optional[RiskLevel] = None,
               error_code: Optional[str] = None) -> PermissionResult:
        return PermissionResult(Decision.BLOCKED, action_class, risk, reason,
                                hard_blocked=True, error_code=error_code)

    # -- scopes -------------------------------------------------------------

    def _check_filesystem_scope(self, request: ActionRequest) -> Optional[str]:
        """Return None if in scope, else a reason string."""
        fs = request.filesystem_scope
        if fs is None or fs.mode == FsScopeMode.NONE:
            return None
        requested = set(fs.paths_class or [])
        if not requested:
            return None
        if fs.mode in (FsScopeMode.READ, FsScopeMode.READ_WRITE):
            if not requested.issubset(self._scope.fs_read):
                return "filesystem read scope escape"
        if fs.mode in (FsScopeMode.WRITE, FsScopeMode.READ_WRITE):
            if not requested.issubset(self._scope.fs_write):
                return "filesystem write scope escape"
        return None

    def _check_network_scope(self, request: ActionRequest) -> Optional[str]:
        net = request.network_scope
        if net is None or net.mode == NetworkScopeMode.NONE:
            return None
        if net.mode == NetworkScopeMode.LOOPBACK:
            if not self._scope.network_loopback:
                return "network loopback not granted"
            return None
        if net.mode == NetworkScopeMode.CLOUD_EGRESS:
            requested = set(net.endpoints_class or [])
            if not requested.issubset(self._scope.network_egress):
                return "network egress scope escape (loopback-only default)"
            return None
        return None

    def _check_process_scope(self, request: ActionRequest) -> Optional[str]:
        if request.process_scope is None:
            return None
        requested = set(request.process_scope.allowed_executables_class or [])
        if requested and not requested.issubset(self._scope.process):
            return "process execution scope escape"
        return None

    # -- hard blocks --------------------------------------------------------

    # Stable, auditable error code for identity-role actions. Fixed value so
    # callers and audits can rely on it across releases (security closure F-W02).
    IDENTITY_HARD_BLOCK_ERROR_CODE = "E_IDENTITY_HARD_BLOCKED"

    # Stable, auditable error code for unknown actions (R1 closure).
    # UNKNOWN_ACTION is an EXPLICIT_REJECT: never mapped to PROCESS_EXEC or any
    # other known action, never downgraded, never overridable.
    UNKNOWN_ACTION_ERROR_CODE = "E_UNKNOWN_ACTION"

    def _hard_block_reason(self, request: ActionRequest, match: RuleMatch) -> Optional[PermissionResult]:
        op = (request.operation or "").lower()
        # R1 closure: UNKNOWN_ACTION is EXPLICIT_REJECT. It is rejected BEFORE
        # any known-action policy, any capability grant, any approval/owner
        # check, and any confirmation channel. It must NEVER create PROCESS_EXEC,
        # never create any known action, never be coerced or downgraded, and
        # must always carry the stable error code E_UNKNOWN_ACTION.
        if match.action_class == ActionClass.UNKNOWN_ACTION:
            return self._block(
                f"{self.UNKNOWN_ACTION_ERROR_CODE}: unknown action explicitly rejected",
                ActionClass.UNKNOWN_ACTION, RiskLevel.NOT_APPLICABLE,
                error_code=self.UNKNOWN_ACTION_ERROR_CODE,
            )
        # arbitrary shell: any operation routed to shell wrappers
        if any(k in op for k in ("shell", "powershell", "cmd", "bash", "pwsh", "run(")):
            return self._block(
                "arbitrary shell execution hard-blocked",
                ActionClass.PROCESS_EXEC, RiskLevel.HIGH,
            )
        # identity / allowlist / owner_allowlist / credential-rotation actions:
        # explicit hard block, independent of owner status, capabilities, or the
        # confirmation channel. Must never be downgraded to a high-risk
        # owner-check path (security closure F-W02).
        if match.action_class == ActionClass.IDENTITY_ACTION:
            return self._block(
                f"{self.IDENTITY_HARD_BLOCK_ERROR_CODE}: identity action hard-blocked in the current release candidate",
                match.action_class, match.risk_level,
            )
        if match.action_class == ActionClass.ADMIN_ELEVATION:
            return self._block("admin elevation hard-blocked", match.action_class, match.risk_level)
        if match.action_class == ActionClass.PROCESS_EXEC:
            return self._block("process execution hard-blocked in the current release candidate",
                               match.action_class, match.risk_level)
        if match.action_class == ActionClass.FINANCIAL_ACTION:
            return self._block("financial action hard-blocked in the current release candidate",
                               match.action_class, match.risk_level)
        if match.risk_level == RiskLevel.CRITICAL:
            return self._block(f"critical action hard-blocked: {match.action_class.value}",
                               match.action_class, match.risk_level)
        # General policy fallback: any action class the policy table marks as
        # hard_blocked is blocked here, even if not covered by the explicit
        # cases above. Keeps policy declarations authoritative.
        if match.hard_blocked:
            return self._block(f"policy hard-blocked: {match.action_class.value}",
                               match.action_class, match.risk_level)
        return None

    # -- idempotency / replay ----------------------------------------------

    def _check_replay(self, request: ActionRequest) -> Optional[PermissionResult]:
        # Replay: the same action_id submitted twice (without an idempotency
        # key returning a cached result) is rejected.
        if request.action_id in self._seen_action_ids:
            return PermissionResult(Decision.DENY, None, None, "replay detected",
                                    is_replay=True)
        # Idempotent retry: same idempotency_key returns the cached decision.
        if request.idempotency_key and request.idempotency_key in self._idempotency_results:
            cached = self._idempotency_results[request.idempotency_key]
            return PermissionResult(Decision.ALLOW, cached.action_class, cached.risk_level,
                                    "idempotent replay (cached decision)", is_replay=True)
        return None

    # -- authorization ------------------------------------------------------

    def authorize(self, request: ActionRequest) -> PermissionResult:
        """Deny-by-default authorization of a single ActionRequest."""
        # Replay detection first (idempotent replays allowed only with a key)
        replay = self._check_replay(request)
        if replay is not None:
            # Either a genuine replay (DENY) or an idempotent replay (cached
            # ALLOW). Both must be returned immediately so the cached decision
            # is authoritative and the action is not re-evaluated.
            return replay
        # Record this action as seen so a genuine duplicate is rejected later.
        self._seen_action_ids.add(request.action_id)

        match = self._risk.evaluate(request)

        # Hard blocks: critical / admin / shell / process exec
        blocked = self._hard_block_reason(request, match)
        if blocked is not None:
            self._idempotency_results.setdefault(request.idempotency_key, blocked)
            return blocked

        # Deny-by-default: capability allowlist
        cap_tokens = set(request.required_permissions or [])
        if cap_tokens and not cap_tokens.issubset(self._capabilities):
            missing = sorted(cap_tokens - self._capabilities)
            return self._deny(f"capability not granted: {','.join(missing)}",
                              match.action_class, match.risk_level)

        # Scope checks
        fs_err = self._check_filesystem_scope(request)
        if fs_err:
            return self._deny(fs_err, match.action_class, match.risk_level)
        net_err = self._check_network_scope(request)
        if net_err:
            return self._deny(net_err, match.action_class, match.risk_level)
        proc_err = self._check_process_scope(request)
        if proc_err:
            return self._deny(proc_err, match.action_class, match.risk_level)

        # High-risk confirmation
        if self._high_risk_confirmation and match.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if match.confirmation_kind == ConfirmationKind.OWNER_APPROVAL and not self._is_owner:
                return self._deny("owner-only action denied (not owner)",
                                  match.action_class, match.risk_level,
                                  confirm=match.confirmation_kind)
            # the release candidate has no real confirmation channel; HIGH actions require
            # explicit confirmation flag carried on the request.
            if not request.approval_required and match.risk_level == RiskLevel.HIGH:
                return PermissionResult(
                    Decision.CONFIRMATION_REQUIRED, match.action_class, match.risk_level,
                    "high-risk action requires confirmation", hard_blocked=False,
                    confirmation_kind=match.confirmation_kind,
                )
            # If approval_required was set, treat as confirmed in this engine;
            # the orchestrator validates a confirmation id separately.
            if match.risk_level == RiskLevel.CRITICAL:
                return self._block("critical action hard-blocked", match.action_class, match.risk_level)

        result = PermissionResult(Decision.ALLOW, match.action_class, match.risk_level,
                                  match.reason, confirmation_kind=match.confirmation_kind)
        self._idempotency_results.setdefault(request.idempotency_key, result)
        return result

    def reset_seen_ids(self) -> None:
        self._seen_action_ids.clear()
        self._idempotency_results.clear()
