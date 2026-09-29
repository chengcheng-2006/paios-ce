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

from dataclasses import dataclass, replace
from enum import Enum
from threading import RLock
from typing import Dict, Iterable, Optional, Set

from ..protocols import (
    ActionRequest,
    ConfirmationKind,
    FsScopeMode,
    NetworkScopeMode,
    RiskLevel,
)
from ..state import (
    AuthorizationReplayOutcomeKind,
    DurableAuthorizationDecision,
    SQLiteDurableStateStore,
    StateStoreError,
    StateStoreValidationError,
)
from .policy import ActionClass, ActionRiskPolicy, PolicyDecision
from .identity import (
    AuthorizationIdentity,
    CanonicalizationError,
    PrincipalContext,
    authorization_identity,
)


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
    trusted_principal_id: Optional[str] = None
    request_fingerprint: Optional[str] = None
    security_context_fingerprint: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


@dataclass(frozen=True)
class AuthorizationReplayRecord:
    """Complete in-memory snapshot for authorization-level replay only."""

    identity: AuthorizationIdentity
    result: PermissionResult


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

    def security_context(self) -> dict[str, object]:
        """Expose the existing static policy as replay-relevant context."""

        return self._policy.security_context()


class PermissionEngine:
    """Authorizes ActionRequests under a capability + scope grant."""

    def __init__(
        self,
        capabilities: Iterable[str] = (),
        owner_allowlist: Iterable[str] = (),
        principal_id: str = "principal:example.invalid/user-1",
        scope_guard: Optional[ScopeGuard] = None,
        high_risk_confirmation_enabled: bool = True,
        policy: Optional[ActionRiskPolicy] = None,
        principal_context: Optional[PrincipalContext] = None,
        durable_state_store: Optional[SQLiteDurableStateStore] = None,
    ) -> None:
        self._capabilities: Set[str] = set(capabilities)
        self._owners: Set[str] = set(owner_allowlist)
        if principal_context is not None and not isinstance(principal_context, PrincipalContext):
            raise TypeError("principal_context must be a PrincipalContext")
        self._default_principal = principal_context or PrincipalContext(principal_id)
        self._scope = scope_guard or ScopeGuard()
        self._high_risk_confirmation = high_risk_confirmation_enabled
        self._risk = RiskEngine(policy)
        self._durable_state_store = durable_state_store
        self._seen_request_ids: Set[str] = set()
        self._seen_action_ids: Set[str] = set()
        self._authorization_replays: Dict[str, AuthorizationReplayRecord] = {}
        self._replay_lock = RLock()

    # -- capability / principal plumbing -----------------------------------

    def is_owner(self, principal_context: Optional[PrincipalContext] = None) -> bool:
        """Whether the trusted runtime context is currently allowlisted."""

        principal = self._resolve_principal(principal_context)
        return principal is not None and principal.principal_id in self._owners

    def has_capability(self, capability: str) -> bool:
        return capability in self._capabilities

    @property
    def durable_state_store(self) -> Optional[SQLiteDurableStateStore]:
        """The optional Phase 2 durable authority configured for this engine."""

        return self._durable_state_store

    def _resolve_principal(
        self, principal_context: Optional[PrincipalContext]
    ) -> Optional[PrincipalContext]:
        if principal_context is None:
            return self._default_principal
        return principal_context if isinstance(principal_context, PrincipalContext) else None

    def _security_context(self) -> dict[str, object]:
        """Current, real authorization inputs; no speculative policy layer."""

        return {
            "capabilities": sorted(self._capabilities),
            "owner_allowlist": sorted(self._owners),
            "scope": {
                "fs_read": sorted(self._scope.fs_read),
                "fs_write": sorted(self._scope.fs_write),
                "network_loopback": self._scope.network_loopback,
                "network_egress": sorted(self._scope.network_egress),
                "process": sorted(self._scope.process),
            },
            "high_risk_confirmation_enabled": self._high_risk_confirmation,
            "policy": self._risk.security_context(),
        }

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

    IDEMPOTENCY_KEY_INVALID_ERROR_CODE = "E_IDEMPOTENCY_KEY_INVALID"
    IDEMPOTENCY_CONFLICT_ERROR_CODE = "E_IDEMPOTENCY_KEY_REUSE_MISMATCH"
    IDEMPOTENCY_FINGERPRINT_ERROR_CODE = "E_IDEMPOTENCY_FINGERPRINT_INVALID"
    IDEMPOTENCY_RECORD_INVALID_ERROR_CODE = "E_IDEMPOTENCY_REPLAY_RECORD_INVALID"
    DURABLE_STATE_UNAVAILABLE_ERROR_CODE = "E_DURABLE_STATE_UNAVAILABLE"
    TRUSTED_PRINCIPAL_INVALID_ERROR_CODE = "E_TRUSTED_PRINCIPAL_INVALID"

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

    def _with_identity(
        self, result: PermissionResult, identity: Optional[AuthorizationIdentity]
    ) -> PermissionResult:
        if identity is None:
            return result
        return replace(
            result,
            trusted_principal_id=identity.principal_id,
            request_fingerprint=identity.request_fingerprint,
            security_context_fingerprint=identity.security_context_fingerprint,
        )

    def _check_replay(
        self, request: ActionRequest, identity: Optional[AuthorizationIdentity]
    ) -> Optional[PermissionResult]:
        """Return an exact snapshot or a fail-closed replay result.

        This method is called while ``_replay_lock`` is held, so lookup,
        comparison, evaluation, and storage form one process-local critical
        section.
        """

        key = request.idempotency_key
        if key is not None:
            if identity is None:
                return self._block(
                    "idempotency fingerprint could not be established",
                    error_code=self.IDEMPOTENCY_FINGERPRINT_ERROR_CODE,
                )
            record = self._authorization_replays.get(key)
            if record is None:
                return None
            if not isinstance(record, AuthorizationReplayRecord):
                return self._with_identity(
                    self._block(
                        "idempotency replay record is invalid",
                        error_code=self.IDEMPOTENCY_RECORD_INVALID_ERROR_CODE,
                    ),
                    identity,
                )
            if record.identity == identity:
                return replace(record.result, is_replay=True)
            return self._with_identity(
                self._block(
                    "idempotency key reuse does not match the original authorization identity",
                    error_code=self.IDEMPOTENCY_CONFLICT_ERROR_CODE,
                ),
                identity,
            )

        # Keyless calls retain the existing duplicate action-id protection but
        # are intentionally not stored as authorization replays.
        if request.action_id in self._seen_action_ids:
            return PermissionResult(Decision.DENY, None, None, "replay detected",
                                    is_replay=True)
        return None

    @staticmethod
    def _durable_snapshot(result: PermissionResult) -> DurableAuthorizationDecision:
        """Convert the redacted authorization result to explicit store fields."""

        return DurableAuthorizationDecision(
            decision=result.decision.value,
            action_class=result.action_class.value if result.action_class else None,
            risk_level=result.risk_level.value if result.risk_level else None,
            reason=result.reason,
            hard_blocked=result.hard_blocked,
            confirmation_kind=result.confirmation_kind.value,
            error_code=result.error_code,
        )

    def _permission_from_durable_snapshot(
        self,
        snapshot: DurableAuthorizationDecision,
        identity: AuthorizationIdentity,
    ) -> PermissionResult:
        """Validate a stored decision rather than trusting arbitrary DB strings."""

        try:
            action_class = None if snapshot.action_class is None else ActionClass(snapshot.action_class)
            risk_level = None if snapshot.risk_level is None else RiskLevel(snapshot.risk_level)
            return PermissionResult(
                decision=Decision(snapshot.decision),
                action_class=action_class,
                risk_level=risk_level,
                reason=snapshot.reason,
                hard_blocked=snapshot.hard_blocked,
                confirmation_kind=ConfirmationKind(snapshot.confirmation_kind),
                is_replay=True,
                error_code=snapshot.error_code,
                trusted_principal_id=identity.principal_id,
                request_fingerprint=identity.request_fingerprint,
                security_context_fingerprint=identity.security_context_fingerprint,
            )
        except (TypeError, ValueError):
            return self._with_identity(
                self._block(
                    "durable idempotency replay record is invalid",
                    error_code=self.IDEMPOTENCY_RECORD_INVALID_ERROR_CODE,
                ),
                identity,
            )

    def _authorize_durably(
        self,
        request: ActionRequest,
        principal: PrincipalContext,
        identity: AuthorizationIdentity,
    ) -> PermissionResult:
        """Run keyed authorization under the cross-process SQLite authority."""

        fresh: Optional[PermissionResult] = None

        def evaluate_and_snapshot() -> DurableAuthorizationDecision:
            nonlocal fresh
            fresh = self._with_identity(self._evaluate(request, principal), identity)
            return self._durable_snapshot(fresh)

        try:
            outcome = self._durable_state_store.authorize_replay(  # type: ignore[union-attr]
                identity, evaluate_and_snapshot
            )
        except StateStoreValidationError:
            return self._with_identity(
                self._block(
                    "durable idempotency replay record is invalid",
                    error_code=self.IDEMPOTENCY_RECORD_INVALID_ERROR_CODE,
                ),
                identity,
            )
        except StateStoreError:
            return self._with_identity(
                self._block(
                    "durable state authority is unavailable",
                    error_code=self.DURABLE_STATE_UNAVAILABLE_ERROR_CODE,
                ),
                identity,
            )
        if outcome.kind is AuthorizationReplayOutcomeKind.CONFLICT:
            return self._with_identity(
                self._block(
                    "idempotency key reuse does not match the original authorization identity",
                    error_code=self.IDEMPOTENCY_CONFLICT_ERROR_CODE,
                ),
                identity,
            )
        if outcome.kind is AuthorizationReplayOutcomeKind.REPLAY:
            if outcome.decision is None:
                return self._with_identity(
                    self._block(
                        "durable idempotency replay record is invalid",
                        error_code=self.IDEMPOTENCY_RECORD_INVALID_ERROR_CODE,
                    ),
                    identity,
                )
            return self._permission_from_durable_snapshot(outcome.decision, identity)
        if fresh is None:
            return self._with_identity(
                self._block(
                    "durable authorization record could not be created",
                    error_code=self.DURABLE_STATE_UNAVAILABLE_ERROR_CODE,
                ),
                identity,
            )
        return fresh

    # -- authorization ------------------------------------------------------

    def _evaluate(self, request: ActionRequest, principal: PrincipalContext) -> PermissionResult:
        """Evaluate a previously admitted, non-replay authorization request."""

        match = self._risk.evaluate(request)

        # Hard blocks: critical / admin / shell / process exec
        blocked = self._hard_block_reason(request, match)
        if blocked is not None:
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
            if match.confirmation_kind == ConfirmationKind.OWNER_APPROVAL and not self.is_owner(principal):
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
        return result

    def authorize(
        self,
        request: ActionRequest,
        *,
        principal_context: Optional[PrincipalContext] = None,
    ) -> PermissionResult:
        """Deny-by-default authorization using a trusted runtime principal.

        ``principal_context`` is deliberately separate from ``ActionRequest``.
        An untrusted model cannot grant itself identity by placing a similarly
        named value inside action parameters.
        """

        with self._replay_lock:
            principal = self._resolve_principal(principal_context)
            if principal is None:
                return self._block(
                    "trusted principal context is invalid",
                    error_code=self.TRUSTED_PRINCIPAL_INVALID_ERROR_CODE,
                )

            key = request.idempotency_key
            if key is not None and (not isinstance(key, str) or not key):
                return self._block(
                    "idempotency key is invalid",
                    error_code=self.IDEMPOTENCY_KEY_INVALID_ERROR_CODE,
                )

            identity: Optional[AuthorizationIdentity] = None
            if key is not None:
                try:
                    identity = authorization_identity(
                        request, principal, self._security_context()
                    )
                except CanonicalizationError:
                    return self._block(
                        "idempotency fingerprint could not be established",
                        error_code=self.IDEMPOTENCY_FINGERPRINT_ERROR_CODE,
                    )

            if identity is not None and self._durable_state_store is not None:
                return self._authorize_durably(request, principal, identity)

            replay = self._check_replay(request, identity)
            if replay is not None:
                return replay

            self._seen_action_ids.add(request.action_id)
            result = self._with_identity(self._evaluate(request, principal), identity)
            if identity is not None:
                self._authorization_replays[identity.idempotency_key] = AuthorizationReplayRecord(
                    identity=identity,
                    result=replace(result, is_replay=False),
                )
            return result

    def reset_seen_ids(self) -> None:
        with self._replay_lock:
            self._seen_action_ids.clear()
            self._authorization_replays.clear()
