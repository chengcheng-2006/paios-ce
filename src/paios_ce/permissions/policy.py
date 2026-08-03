"""Action classification and risk policy (deny-by-default).

Action classes follow the Phase 3 execution prompt section 12:
READ_LOCAL, WRITE_LOCAL, DELETE_LOCAL, NETWORK_READ, NETWORK_WRITE,
PROCESS_EXEC, ADMIN_ELEVATION, SECRET_ACCESS, EXTERNAL_MESSAGE,
FINANCIAL_ACTION, IDENTITY_ACTION.

UNKNOWN_ACTION is the explicit rejection class (Phase 3R-R1): an operation
that matches no classifier keyword is UNKNOWN_ACTION, NEVER mapped to a
known action, NEVER coerced to PROCESS_EXEC. It is hard-blocked with the
stable error code E_UNKNOWN_ACTION and risk NOT_APPLICABLE.

Risk levels: LOW / MEDIUM / HIGH / CRITICAL / NOT_APPLICABLE.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Dict, FrozenSet, Optional

from ..protocols import ConfirmationKind, RiskLevel


class ActionClass(str, Enum):
    READ_LOCAL = "READ_LOCAL"
    WRITE_LOCAL = "WRITE_LOCAL"
    DELETE_LOCAL = "DELETE_LOCAL"
    NETWORK_READ = "NETWORK_READ"
    NETWORK_WRITE = "NETWORK_WRITE"
    PROCESS_EXEC = "PROCESS_EXEC"
    ADMIN_ELEVATION = "ADMIN_ELEVATION"
    SECRET_ACCESS = "SECRET_ACCESS"
    EXTERNAL_MESSAGE = "EXTERNAL_MESSAGE"
    FINANCIAL_ACTION = "FINANCIAL_ACTION"
    IDENTITY_ACTION = "IDENTITY_ACTION"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"


@dataclass(frozen=True)
class PolicyDecision:
    """The policy-layer decision for an action."""

    action_class: ActionClass
    risk_level: RiskLevel
    requires_confirmation: bool
    confirmation_kind: ConfirmationKind
    owner_only: bool
    hard_blocked: bool
    reason: str


@dataclass
class ActionRiskPolicy:
    """Static risk table for the Phase 3 action classes.

    CRITICAL actions are hard-blocked in Phase 3 (no real execution is
    permitted). ADMIN_ELEVATION and arbitrary PROCESS_EXEC are hard-blocked.
    """

    _table: Dict[ActionClass, PolicyDecision] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._table = {
            ActionClass.READ_LOCAL: PolicyDecision(
                ActionClass.READ_LOCAL, RiskLevel.LOW, False, ConfirmationKind.NONE,
                False, False, "read local within granted scope",
            ),
            ActionClass.WRITE_LOCAL: PolicyDecision(
                ActionClass.WRITE_LOCAL, RiskLevel.MEDIUM, False, ConfirmationKind.NONE,
                False, False, "write local within granted scope",
            ),
            ActionClass.DELETE_LOCAL: PolicyDecision(
                ActionClass.DELETE_LOCAL, RiskLevel.CRITICAL, True, ConfirmationKind.OWNER_APPROVAL,
                True, True, "critical: local delete hard-blocked in Phase 3",
            ),
            ActionClass.NETWORK_READ: PolicyDecision(
                ActionClass.NETWORK_READ, RiskLevel.LOW, False, ConfirmationKind.NONE,
                False, False, "loopback read by default; egress requires grant",
            ),
            ActionClass.NETWORK_WRITE: PolicyDecision(
                ActionClass.NETWORK_WRITE, RiskLevel.HIGH, True, ConfirmationKind.CHANNEL_PROMPT,
                False, False, "external write requires confirmation",
            ),
            ActionClass.PROCESS_EXEC: PolicyDecision(
                ActionClass.PROCESS_EXEC, RiskLevel.HIGH, True, ConfirmationKind.CHANNEL_PROMPT,
                False, True, "process execution hard-blocked in Phase 3 (no real exec)",
            ),
            ActionClass.ADMIN_ELEVATION: PolicyDecision(
                ActionClass.ADMIN_ELEVATION, RiskLevel.CRITICAL, True, ConfirmationKind.OWNER_APPROVAL,
                True, True, "admin elevation hard-blocked in Phase 3",
            ),
            ActionClass.SECRET_ACCESS: PolicyDecision(
                ActionClass.SECRET_ACCESS, RiskLevel.MEDIUM, False, ConfirmationKind.NONE,
                False, False, "credential access via SecretRef only",
            ),
            ActionClass.EXTERNAL_MESSAGE: PolicyDecision(
                ActionClass.EXTERNAL_MESSAGE, RiskLevel.HIGH, True, ConfirmationKind.CHANNEL_PROMPT,
                False, False, "external message requires confirmation",
            ),
            ActionClass.FINANCIAL_ACTION: PolicyDecision(
                ActionClass.FINANCIAL_ACTION, RiskLevel.CRITICAL, True, ConfirmationKind.OWNER_APPROVAL,
                True, True, "critical: financial action hard-blocked in Phase 3",
            ),
            ActionClass.IDENTITY_ACTION: PolicyDecision(
                ActionClass.IDENTITY_ACTION, RiskLevel.HIGH, True, ConfirmationKind.OWNER_APPROVAL,
                True, True, "identity action hard-blocked in Phase 3",
            ),
            # Phase 3R-R1: UNKNOWN_ACTION is EXPLICIT_REJECT. It is NOT mapped
            # to PROCESS_EXEC or any other known action, is NOT overridable by
            # owner/approval/capability/config, and carries risk NOT_APPLICABLE.
            ActionClass.UNKNOWN_ACTION: PolicyDecision(
                ActionClass.UNKNOWN_ACTION, RiskLevel.NOT_APPLICABLE, False, ConfirmationKind.NONE,
                True, True, "E_UNKNOWN_ACTION: unknown action explicitly rejected",
            ),
        }

    def lookup(self, action_class: ActionClass) -> PolicyDecision:
        return self._table.get(
            action_class,
            PolicyDecision(
                action_class, RiskLevel.HIGH, True, ConfirmationKind.CHANNEL_PROMPT,
                True, True, "unknown action class: denied by default",
            ),
        )


    @staticmethod
    def _tokenize(s: str) -> FrozenSet[str]:
        """Split a string into lowercase alphanumeric tokens (non-alnum = delimiter).

        "upload_data" -> frozenset({"upload", "data"}); "read_file" ->
        frozenset({"read", "file"}). Empty strings are discarded.
        """
        return frozenset(t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t)

    @staticmethod
    def _token_match(target: str, keywords) -> bool:
        """Token-based keyword matching (Phase 3R-R1A Advisory-C fix).

        A keyword matches if and only if every token of the keyword is present
        as a token in the target string. This prevents substring false-positives:
        "load" does NOT match "upload" because "upload" is a single token, not
        "up"+"load". Similarly "read" does not match "already_done" because
        "already" is a single token. Multi-word keywords like "install_service"
        match when both "install" and "service" are present as tokens.

        The special pattern "run(" is checked with a literal substring to
        preserve its defensive intent (function-call syntax detection).
        """
        target_tokens = ActionRiskPolicy._tokenize(target)
        for kw in keywords:
            if kw == "run(":
                # Defensive literal pattern for call syntax; not a token keyword.
                if "run(" in target:
                    return True
                continue
            kw_tokens = ActionRiskPolicy._tokenize(kw)
            if kw_tokens and kw_tokens.issubset(target_tokens):
                return True
        return False

    @staticmethod
    def classify(operation: str, permissions: FrozenSet[str], network_mode: str) -> ActionClass:
        """Classify an operation into an ActionClass.

        Heuristic, deterministic, deny-biased. An operation that matches NO
        keyword is classified as ActionClass.UNKNOWN_ACTION and explicitly
        rejected — it is NEVER mapped to PROCESS_EXEC or any other known
        action (Phase 3R-R1 UNKNOWN_ACTION = EXPLICIT_REJECT).

          - admin / elevate / install_service -> ADMIN_ELEVATION
          - shell / exec / run / spawn / powershell / cmd / bash -> PROCESS_EXEC
          - delete / remove / purge / wipe -> DELETE_LOCAL
          - financial / pay / transfer / invoice -> FINANCIAL_ACTION
          - identity / allowlist / owner_allowlist / credential rotate -> IDENTITY_ACTION
          - send message / post / notify external -> EXTERNAL_MESSAGE
          - cloud egress -> NETWORK_WRITE
          - read / list / stat / get -> READ_LOCAL
          - write / append / create / overwrite / save -> WRITE_LOCAL
          - default: UNKNOWN_ACTION (explicit reject, E_UNKNOWN_ACTION)
        """
        # Phase 3R-R1A (Advisory-C fix): keyword matching uses TOKEN-based
        # comparison, not substring. This prevents false-positive coercion where
        # a read keyword like "load" matches the substring inside "upload", or
        # "read" matches inside "already_done". A keyword matches only when its
        # complete token(s) are present as discrete tokens in the operation or
        # permission string. This ensures upload_*, download_*, sync_* and other
        # unregistered prefixes are correctly classified as UNKNOWN_ACTION rather
        # than silently coerced to a known action class.
        if (ActionRiskPolicy._token_match(operation, ("admin", "elevate", "install_service", "elevation"))
                or any(ActionRiskPolicy._token_match(p, ("admin", "elevate", "install_service", "elevation"))
                       for p in (permissions or frozenset()))):
            return ActionClass.ADMIN_ELEVATION
        if ActionRiskPolicy._token_match(operation, ("shell", "exec", "spawn", "powershell", "cmd", "bash", "pwsh", "run(")):
            return ActionClass.PROCESS_EXEC
        if ActionRiskPolicy._token_match(operation, ("delete", "remove", "purge", "wipe", "truncate")):
            return ActionClass.DELETE_LOCAL
        if ActionRiskPolicy._token_match(operation, ("pay", "transfer", "invoice", "payment", "refund")):
            return ActionClass.FINANCIAL_ACTION
        if ActionRiskPolicy._token_match(operation, ("identity", "allowlist", "owner_allowlist", "rotate_credential", "rotate")):
            return ActionClass.IDENTITY_ACTION
        if ActionRiskPolicy._token_match(operation, ("send", "notify", "message", "post", "publish", "email")):
            return ActionClass.EXTERNAL_MESSAGE
        # Phase 3R-R1 (independent-validator finding): the network-mode shortcut
        # MUST NOT fire before the unknown-action fallback, or an operation that
        # matches no keyword is coerced to NETWORK_WRITE under cloud_egress.
        # The network mode is applied to KEYWORD-MATCHED read/write operations
        # only; an operation with no keyword at all is UNKNOWN_ACTION regardless
        # of network_mode. This also stops read ops under egress being forced to
        # NETWORK_WRITE.
        if ActionRiskPolicy._token_match(operation, ("read", "list", "stat", "get", "fetch", "load")):
            return ActionClass.NETWORK_READ if network_mode != "none" else ActionClass.READ_LOCAL
        if ActionRiskPolicy._token_match(operation, ("write", "append", "create", "overwrite", "save", "put", "store")):
            return ActionClass.NETWORK_WRITE if network_mode == "cloud_egress" else ActionClass.WRITE_LOCAL
        # Phase 3R-R1: unknown action is EXPLICIT_REJECT, never mapped to a known action.
        return ActionClass.UNKNOWN_ACTION
