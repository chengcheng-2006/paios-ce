"""State adapters and the Phase 2 durable SQLite state authority.

``SQLiteStateAdapterSkeleton`` remains the legacy interface stub.  The
explicit ``SQLiteDurableStateStore`` is the versioned authority for Phase 2
authorization and recovery facts; it is not a generic key-value replacement.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .adapter import NoopStateAdapter, StateAdapter, SQLiteStateAdapterSkeleton
from .durable import (
    ActionState,
    AuthorizationReplayOutcomeKind,
    Checkpoint,
    DurableAuthorizationDecision,
    DurableAuthorizationReplay,
    JournalEntry,
    JournalEvent,
    ReconciliationObservation,
    ReconciliationResult,
    TaskVerification,
    VerificationStatus,
    RecoveryClassification,
    RecoveryItem,
    SQLiteDurabilitySettings,
    SQLiteDurableStateStore,
    StateStoreError,
    StateStoreSchemaError,
    StateStoreUnavailable,
    StateStoreValidationError,
    StateTransitionError,
)
from .private_files import (
    PrivateFileSecurityError,
    PrivateFileSecurityStatus,
    ensure_private_file,
    harden_private_file,
    verify_private_file,
)

__all__ = [
    "ActionState",
    "AuthorizationReplayOutcomeKind",
    "Checkpoint",
    "DurableAuthorizationDecision",
    "DurableAuthorizationReplay",
    "JournalEntry",
    "JournalEvent",
    "NoopStateAdapter",
    "PrivateFileSecurityError",
    "PrivateFileSecurityStatus",
    "ReconciliationObservation",
    "ReconciliationResult",
    "RecoveryClassification",
    "RecoveryItem",
    "SQLiteDurabilitySettings",
    "SQLiteDurableStateStore",
    "SQLiteStateAdapterSkeleton",
    "StateAdapter",
    "StateStoreError",
    "StateStoreSchemaError",
    "StateStoreUnavailable",
    "StateStoreValidationError",
    "StateTransitionError",
    "TaskVerification",
    "VerificationStatus",
    "ensure_private_file",
    "harden_private_file",
    "verify_private_file",
]
