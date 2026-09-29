"""Versioned SQLite durable state authority for Astron Phase 2.

This module persists only recovery-relevant, non-secret facts.  It is not a
generic key-value store and never serializes ActionRequest parameters or an
executor result payload.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Callable, Iterator, Optional

from .private_files import (
    PrivateFileSecurityError,
    ensure_private_file,
    verify_private_file,
)

if TYPE_CHECKING:
    from ..permissions.identity import AuthorizationIdentity


class StateStoreError(RuntimeError):
    """Base class for state authority failures that must fail closed."""


class StateStoreUnavailable(StateStoreError):
    """SQLite cannot currently be used as the durable state authority."""


class StateStoreSchemaError(StateStoreError):
    """The database schema is malformed, unsupported, or incomplete."""


class StateStoreValidationError(StateStoreError):
    """A durable record has fields outside the supported state contract."""


class StateTransitionError(StateStoreError):
    """A requested action-state transition is not safe or valid."""


class AuthorizationReplayOutcomeKind(str, Enum):
    STORED = "stored"
    REPLAY = "replay"
    CONFLICT = "conflict"


class ActionState(str, Enum):
    RECORDED = "RECORDED"
    AUTHORIZED = "AUTHORIZED"
    ATTEMPT_STARTED = "ATTEMPT_STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"
    RETRY_ELIGIBLE = "RETRY_ELIGIBLE"


class RecoveryClassification(str, Enum):
    NO_ATTEMPT = "NO_ATTEMPT"
    SAFE_TO_CONTINUE = "SAFE_TO_CONTINUE"
    TERMINAL_SUCCESS = "TERMINAL_SUCCESS"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"


class ReconciliationObservation(str, Enum):
    CONFIRMED_SUCCEEDED = "CONFIRMED_SUCCEEDED"
    CONFIRMED_NOT_APPLIED = "CONFIRMED_NOT_APPLIED"
    CONFIRMED_FAILED = "CONFIRMED_FAILED"
    NO_EVIDENCE = "NO_EVIDENCE"


class VerificationStatus(str, Enum):
    """Task completion fact written only by the trusted Phase 3 verifier."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DurableAuthorizationDecision:
    """A validated, deliberately non-secret authorization decision snapshot."""

    decision: str
    action_class: Optional[str]
    risk_level: Optional[str]
    reason: str
    hard_blocked: bool
    confirmation_kind: str
    error_code: Optional[str]


@dataclass(frozen=True)
class DurableAuthorizationReplay:
    kind: AuthorizationReplayOutcomeKind
    decision: Optional[DurableAuthorizationDecision]


@dataclass(frozen=True)
class JournalEntry:
    journal_id: str
    task_id: str
    action_identity: str
    idempotency_key: str
    principal_id: str
    request_fingerprint: str
    security_context_fingerprint: str
    authorization_decision: str
    current_state: ActionState
    journal_sequence: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class JournalEvent:
    journal_id: str
    sequence: int
    state: ActionState
    event_kind: str
    event_at: str


@dataclass(frozen=True)
class Checkpoint:
    task_id: str
    runtime_state: str
    journal_id: Optional[str]
    journal_sequence: Optional[int]
    checkpoint_sequence: int
    created_at: str


@dataclass(frozen=True)
class RecoveryItem:
    journal: Optional[JournalEntry]
    classification: RecoveryClassification


@dataclass(frozen=True)
class ReconciliationResult:
    journal: JournalEntry
    observation: ReconciliationObservation


@dataclass(frozen=True)
class TaskVerification:
    """Redacted deterministic verifier result persisted for one task."""

    task_id: str
    status: VerificationStatus
    reason_code: str
    verifier_version: str
    evidence: dict[str, object]
    verification_sequence: int
    verified_at: str


@dataclass(frozen=True)
class SQLiteDurabilitySettings:
    journal_mode: str
    synchronous_mode: str
    foreign_keys: bool
    busy_timeout_ms: int


_LATEST_SCHEMA_VERSION = 2
_SUPPORTED_DECISIONS = {"allow", "deny", "blocked", "confirmation_required"}
_TERMINAL_STATES = {ActionState.SUCCEEDED, ActionState.FAILED}
_SAFE_TO_CONTINUE_STATES = {
    ActionState.RECORDED,
    ActionState.AUTHORIZED,
    ActionState.RETRY_ELIGIBLE,
}


def _utcnow() -> str:
    """Return a stable UTC timestamp without accepting caller-controlled time."""

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _action_identity(identity: AuthorizationIdentity) -> str:
    """Derive a stable journal identity from the Phase 1 identity fields."""

    payload = {
        "format": "astron.durable-action-identity.v1",
        "idempotency_key": identity.idempotency_key,
        "principal_id": identity.principal_id,
        "request_fingerprint": identity.request_fingerprint,
        "security_context_fingerprint": identity.security_context_fingerprint,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SQLiteDurableStateStore:
    """Small local SQLite authority for durable authorization and recovery facts.

    The connection is intentionally owned by one store instance.  Security
    mutations use short ``BEGIN IMMEDIATE`` transactions, which serialize first
    authorization and journal transitions across separately restarted
    processes.  No operation deletes or recreates an existing database.
    """

    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 1000) -> None:
        if not isinstance(busy_timeout_ms, int) or busy_timeout_ms < 1 or busy_timeout_ms > 60_000:
            raise ValueError("busy_timeout_ms must be an integer between 1 and 60000")
        self.path = Path(path)
        if str(path) == ":memory:":
            raise StateStoreUnavailable("an in-memory database is not a durable state authority")
        self._busy_timeout_ms = busy_timeout_ms
        self._conn: Optional[sqlite3.Connection] = None
        self._settings: Optional[SQLiteDurabilitySettings] = None
        self._open()

    def __enter__(self) -> "SQLiteDurableStateStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def settings(self) -> SQLiteDurabilitySettings:
        if self._settings is None:
            raise StateStoreUnavailable("state store is closed")
        return self._settings

    @property
    def closed(self) -> bool:
        return self._conn is None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._settings = None

    def _open(self) -> None:
        self._create_or_verify_private_file()
        try:
            connection = sqlite3.connect(
                str(self.path),
                timeout=self._busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            self._conn = connection
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
            if foreign_keys != 1:
                raise StateStoreUnavailable("SQLite refused foreign_keys=ON")
            actual_timeout = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
            if actual_timeout != self._busy_timeout_ms:
                raise StateStoreUnavailable("SQLite busy timeout could not be verified")
            # Schema validation occurs before changing the database journal
            # mode.  An unsupported database must be observed and rejected,
            # not rewritten merely because a process attempted to open it.
            self._initialize_schema()
            actual_journal_mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]).upper()
            if actual_journal_mode != "WAL":
                raise StateStoreUnavailable("SQLite refused WAL journal mode")
            connection.execute("PRAGMA synchronous = FULL")
            actual_synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
            if actual_synchronous != 2:
                raise StateStoreUnavailable("SQLite refused FULL synchronous mode")
            self._settings = SQLiteDurabilitySettings(
                journal_mode=actual_journal_mode,
                synchronous_mode="FULL",
                foreign_keys=True,
                busy_timeout_ms=actual_timeout,
            )
        except StateStoreError:
            self.close()
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            self.close()
            raise StateStoreUnavailable("durable SQLite state store could not be opened") from exc

    def _create_or_verify_private_file(self) -> None:
        try:
            ensure_private_file(self.path)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                if sidecar.exists():
                    # SQLite sidecars inherit from the already-verified parent
                    # directory. Existing sidecars must still be inspected
                    # before SQLite can open them.
                    verify_private_file(
                        sidecar,
                        require_protected_windows_dacl=False,
                    )
        except PrivateFileSecurityError as exc:
            raise StateStoreUnavailable(
                "state database permissions are not owner-private"
            ) from exc

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StateStoreUnavailable("state store is closed")
        return self._conn

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connection
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("durable state transaction could not begin") from exc
        try:
            yield connection
        except StateStoreError:
            self._rollback_quietly(connection)
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly(connection)
            raise StateStoreUnavailable("durable state transaction failed") from exc
        except Exception:
            self._rollback_quietly(connection)
            raise
        try:
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback_quietly(connection)
            raise StateStoreUnavailable("durable state transaction could not commit") from exc

    @staticmethod
    def _rollback_quietly(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    def _initialize_schema(self) -> None:
        try:
            tables = {
                str(row[0])
                for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("state database cannot be inspected") from exc
        if "schema_metadata" not in tables:
            if tables:
                raise StateStoreSchemaError("database has tables but no schema metadata")
            with self._write_transaction() as connection:
                self._create_schema_v1(connection)
                connection.execute(
                    "INSERT INTO schema_metadata (key, value) VALUES (?, ?)",
                    ("schema_version", "1"),
                )
            with self._write_transaction() as connection:
                self._migrate_v1_to_v2(connection)
                connection.execute(
                    "UPDATE schema_metadata SET value = ? WHERE key = ?",
                    ("2", "schema_version"),
                )
        else:
            version = self._read_schema_version()
            if version > _LATEST_SCHEMA_VERSION:
                raise StateStoreSchemaError("state database schema is newer than this runtime")
            if version < 0:
                raise StateStoreSchemaError("state database schema version is invalid")
            while version < _LATEST_SCHEMA_VERSION:
                if version == 0:
                    with self._write_transaction() as connection:
                        self._migrate_v0_to_v1(connection)
                        connection.execute(
                            "UPDATE schema_metadata SET value = ? WHERE key = ?",
                            ("1", "schema_version"),
                        )
                    version = 1
                elif version == 1:
                    # Validate the prior contract before an additive migration;
                    # never use a migration to paper over a malformed v1 DB.
                    self._validate_schema_v1()
                    with self._write_transaction() as connection:
                        self._migrate_v1_to_v2(connection)
                        connection.execute(
                            "UPDATE schema_metadata SET value = ? WHERE key = ?",
                            ("2", "schema_version"),
                        )
                    version = 2
                else:
                    raise StateStoreSchemaError("state database schema version is unsupported")
        self._validate_schema_v2()

    def _read_schema_version(self) -> int:
        try:
            rows = self._connection.execute(
                "SELECT value FROM schema_metadata WHERE key = ?", ("schema_version",)
            ).fetchall()
        except sqlite3.Error as exc:
            raise StateStoreSchemaError("schema metadata cannot be read") from exc
        if len(rows) != 1:
            raise StateStoreSchemaError("schema version is missing or ambiguous")
        raw = rows[0][0]
        if not isinstance(raw, str) or not raw.isdigit():
            raise StateStoreSchemaError("schema version is malformed")
        return int(raw)

    @staticmethod
    def _create_schema_v1(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE schema_metadata (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)"
        )
        SQLiteDurableStateStore._migrate_v0_to_v1(connection)

    @staticmethod
    def _migrate_v0_to_v1(connection: sqlite3.Connection) -> None:
        """Deterministically install v1 tables for the supported v0 marker."""

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS authorization_replays (
                idempotency_key TEXT PRIMARY KEY NOT NULL,
                principal_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                security_context_fingerprint TEXT NOT NULL,
                decision TEXT NOT NULL,
                action_class TEXT,
                risk_level TEXT,
                reason TEXT NOT NULL,
                hard_blocked INTEGER NOT NULL CHECK (hard_blocked IN (0, 1)),
                confirmation_kind TEXT NOT NULL,
                error_code TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_tasks (
                task_id TEXT PRIMARY KEY NOT NULL,
                runtime_state TEXT NOT NULL,
                active_journal_id TEXT,
                checkpoint_sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS action_journal (
                journal_id TEXT PRIMARY KEY NOT NULL,
                task_id TEXT NOT NULL REFERENCES runtime_tasks(task_id),
                action_identity TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE REFERENCES authorization_replays(idempotency_key),
                principal_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                security_context_fingerprint TEXT NOT NULL,
                authorization_decision TEXT NOT NULL,
                current_state TEXT NOT NULL,
                journal_sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS action_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id TEXT NOT NULL REFERENCES action_journal(journal_id),
                sequence INTEGER NOT NULL,
                state TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                event_at TEXT NOT NULL,
                UNIQUE (journal_id, sequence)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                task_id TEXT PRIMARY KEY NOT NULL REFERENCES runtime_tasks(task_id),
                runtime_state TEXT NOT NULL,
                journal_id TEXT REFERENCES action_journal(journal_id),
                journal_sequence INTEGER,
                checkpoint_sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reconciliation_events (
                reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                journal_id TEXT NOT NULL REFERENCES action_journal(journal_id),
                observation TEXT NOT NULL,
                resulting_state TEXT NOT NULL,
                journal_sequence INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_journal_task ON action_journal(task_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_journal_state ON action_journal(task_id, current_state)"
        )

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        """Add verifier-only durable completion facts without rewriting v1 history."""

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_verifications (
                task_id TEXT PRIMARY KEY NOT NULL REFERENCES runtime_tasks(task_id),
                status TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                verifier_version TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                verification_sequence INTEGER NOT NULL,
                verified_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_verification_events (
                verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL REFERENCES runtime_tasks(task_id),
                verification_sequence INTEGER NOT NULL,
                status TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                verifier_version TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                UNIQUE (task_id, verification_sequence)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_verification_events_task ON task_verification_events(task_id, verification_sequence)"
        )

    @staticmethod
    def _schema_v1_required() -> dict[str, set[str]]:
        return {
            "schema_metadata": {"key", "value"},
            "authorization_replays": {
                "idempotency_key", "principal_id", "request_fingerprint",
                "security_context_fingerprint", "decision", "action_class",
                "risk_level", "reason", "hard_blocked", "confirmation_kind",
                "error_code", "created_at",
            },
            "runtime_tasks": {
                "task_id", "runtime_state", "active_journal_id", "checkpoint_sequence",
                "created_at", "updated_at",
            },
            "action_journal": {
                "journal_id", "task_id", "action_identity", "idempotency_key",
                "principal_id", "request_fingerprint", "security_context_fingerprint",
                "authorization_decision", "current_state", "journal_sequence",
                "created_at", "updated_at",
            },
            "action_events": {"event_id", "journal_id", "sequence", "state", "event_kind", "event_at"},
            "checkpoints": {
                "task_id", "runtime_state", "journal_id", "journal_sequence",
                "checkpoint_sequence", "created_at",
            },
            "reconciliation_events": {
                "reconciliation_id", "journal_id", "observation", "resulting_state",
                "journal_sequence", "created_at",
            },
        }

    def _validate_schema_v1(self) -> None:
        self._validate_required_schema(self._schema_v1_required())

    def _validate_schema_v2(self) -> None:
        required = self._schema_v1_required()
        required.update({
            "task_verifications": {
                "task_id", "status", "reason_code", "verifier_version", "evidence_json",
                "verification_sequence", "verified_at",
            },
            "task_verification_events": {
                "verification_id", "task_id", "verification_sequence", "status", "reason_code",
                "verifier_version", "evidence_json", "verified_at",
            },
        })
        self._validate_required_schema(required)

    def _validate_required_schema(self, required: dict[str, set[str]]) -> None:
        for table, expected_columns in required.items():
            try:
                actual_columns = {
                    str(row[1]) for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
            except sqlite3.Error as exc:
                raise StateStoreSchemaError("state database schema cannot be validated") from exc
            if not expected_columns.issubset(actual_columns):
                raise StateStoreSchemaError(f"state database table {table} is incomplete")

    # -- durable authorization replay -------------------------------------

    def authorize_replay(
        self,
        identity: AuthorizationIdentity,
        decision_supplier: Callable[[], DurableAuthorizationDecision],
    ) -> DurableAuthorizationReplay:
        """Atomically persist or restore one complete authorization decision."""

        self._validate_identity(identity)
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT * FROM authorization_replays WHERE idempotency_key = ?",
                (identity.idempotency_key,),
            ).fetchone()
            if row is not None:
                stored_identity = self._identity_from_authorization_row(row)
                if stored_identity != identity:
                    return DurableAuthorizationReplay(AuthorizationReplayOutcomeKind.CONFLICT, None)
                return DurableAuthorizationReplay(
                    AuthorizationReplayOutcomeKind.REPLAY,
                    self._decision_from_authorization_row(row),
                )
            decision = decision_supplier()
            self._validate_decision(decision)
            connection.execute(
                """
                INSERT INTO authorization_replays (
                    idempotency_key, principal_id, request_fingerprint,
                    security_context_fingerprint, decision, action_class, risk_level,
                    reason, hard_blocked, confirmation_kind, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.idempotency_key,
                    identity.principal_id,
                    identity.request_fingerprint,
                    identity.security_context_fingerprint,
                    decision.decision,
                    decision.action_class,
                    decision.risk_level,
                    decision.reason,
                    int(decision.hard_blocked),
                    decision.confirmation_kind,
                    decision.error_code,
                    _utcnow(),
                ),
            )
            return DurableAuthorizationReplay(AuthorizationReplayOutcomeKind.STORED, decision)

    def authorization_record(self, key: str) -> Optional[DurableAuthorizationDecision]:
        try:
            row = self._connection.execute(
                "SELECT * FROM authorization_replays WHERE idempotency_key = ?", (key,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("durable authorization record cannot be read") from exc
        return None if row is None else self._decision_from_authorization_row(row)

    @staticmethod
    def _validate_identity(identity: AuthorizationIdentity) -> None:
        values = (
            identity.idempotency_key,
            identity.principal_id,
            identity.request_fingerprint,
            identity.security_context_fingerprint,
        )
        if any(not isinstance(value, str) or not value for value in values):
            raise StateStoreValidationError("authorization identity is incomplete")
        if len(identity.request_fingerprint) != 64 or len(identity.security_context_fingerprint) != 64:
            raise StateStoreValidationError("authorization identity fingerprints are invalid")

    @staticmethod
    def _validate_decision(decision: DurableAuthorizationDecision) -> None:
        if decision.decision not in _SUPPORTED_DECISIONS:
            raise StateStoreValidationError("authorization decision is unsupported")
        if not isinstance(decision.reason, str) or not decision.reason:
            raise StateStoreValidationError("authorization reason is invalid")
        if not isinstance(decision.hard_blocked, bool):
            raise StateStoreValidationError("authorization hard_blocked is invalid")
        if not isinstance(decision.confirmation_kind, str) or not decision.confirmation_kind:
            raise StateStoreValidationError("authorization confirmation kind is invalid")
        if decision.action_class is not None and not isinstance(decision.action_class, str):
            raise StateStoreValidationError("authorization action class is invalid")
        if decision.risk_level is not None and not isinstance(decision.risk_level, str):
            raise StateStoreValidationError("authorization risk level is invalid")
        if decision.error_code is not None and not isinstance(decision.error_code, str):
            raise StateStoreValidationError("authorization error code is invalid")

    def _identity_from_authorization_row(self, row: sqlite3.Row) -> AuthorizationIdentity:
        from ..permissions.identity import AuthorizationIdentity

        try:
            identity = AuthorizationIdentity(
                idempotency_key=self._required_text(row, "idempotency_key"),
                principal_id=self._required_text(row, "principal_id"),
                request_fingerprint=self._required_text(row, "request_fingerprint"),
                security_context_fingerprint=self._required_text(row, "security_context_fingerprint"),
            )
            self._validate_identity(identity)
            return identity
        except (KeyError, TypeError, StateStoreError) as exc:
            raise StateStoreValidationError("durable authorization identity record is invalid") from exc

    def _decision_from_authorization_row(self, row: sqlite3.Row) -> DurableAuthorizationDecision:
        try:
            hard_blocked = row["hard_blocked"]
            if hard_blocked not in (0, 1):
                raise StateStoreValidationError("authorization hard_blocked record is invalid")
            decision = DurableAuthorizationDecision(
                decision=self._required_text(row, "decision"),
                action_class=self._optional_text(row, "action_class"),
                risk_level=self._optional_text(row, "risk_level"),
                reason=self._required_text(row, "reason"),
                hard_blocked=bool(hard_blocked),
                confirmation_kind=self._required_text(row, "confirmation_kind"),
                error_code=self._optional_text(row, "error_code"),
            )
            self._validate_decision(decision)
            return decision
        except (KeyError, TypeError, StateStoreError) as exc:
            raise StateStoreValidationError("durable authorization decision record is invalid") from exc

    # -- action journal / checkpoints -------------------------------------

    def prepare_authorized_action(
        self,
        task_id: str,
        identity: AuthorizationIdentity,
        decision: DurableAuthorizationDecision,
    ) -> JournalEntry:
        """Create a permitted journal record and checkpoint, or restore it."""

        self._validate_task_id(task_id)
        self._validate_identity(identity)
        self._validate_decision(decision)
        if decision.decision != "allow":
            raise StateTransitionError("only an allowed authorization can prepare an action journal")
        with self._write_transaction() as connection:
            authorization = connection.execute(
                "SELECT * FROM authorization_replays WHERE idempotency_key = ?",
                (identity.idempotency_key,),
            ).fetchone()
            if authorization is None:
                raise StateStoreValidationError("journal authorization record is missing")
            if self._identity_from_authorization_row(authorization) != identity:
                raise StateTransitionError("journal authorization identity conflicts with durable replay")
            existing = connection.execute(
                "SELECT * FROM action_journal WHERE idempotency_key = ?",
                (identity.idempotency_key,),
            ).fetchone()
            if existing is not None:
                entry = self._journal_from_row(existing)
                if entry.task_id != task_id or entry.action_identity != _action_identity(identity):
                    raise StateTransitionError("idempotency key already belongs to a different journal action")
                return entry
            unresolved = connection.execute(
                """
                SELECT journal_id FROM action_journal
                WHERE task_id = ? AND current_state IN (?, ?)
                """,
                (task_id, ActionState.ATTEMPT_STARTED.value, ActionState.UNCERTAIN.value),
            ).fetchall()
            if unresolved:
                raise StateTransitionError("task already has an unresolved action")
            timestamp = _utcnow()
            journal_id = _action_identity(identity)
            connection.execute(
                """
                INSERT INTO runtime_tasks (
                    task_id, runtime_state, active_journal_id, checkpoint_sequence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    runtime_state = excluded.runtime_state,
                    active_journal_id = excluded.active_journal_id,
                    updated_at = excluded.updated_at
                """,
                (task_id, "RUNNING", journal_id, 0, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO action_journal (
                    journal_id, task_id, action_identity, idempotency_key, principal_id,
                    request_fingerprint, security_context_fingerprint, authorization_decision,
                    current_state, journal_sequence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    journal_id, task_id, journal_id, identity.idempotency_key, identity.principal_id,
                    identity.request_fingerprint, identity.security_context_fingerprint, decision.decision,
                    ActionState.AUTHORIZED.value, 2, timestamp, timestamp,
                ),
            )
            self._append_event(connection, journal_id, 1, ActionState.RECORDED, "JOURNAL_RECORDED", timestamp)
            self._append_event(connection, journal_id, 2, ActionState.AUTHORIZED, "AUTHORIZATION_RECORDED", timestamp)
            self._write_checkpoint(connection, task_id, "RUNNING", journal_id, 2, timestamp)
            return self._journal_from_row(connection.execute(
                "SELECT * FROM action_journal WHERE journal_id = ?", (journal_id,)
            ).fetchone())

    def record_attempt_started(self, journal_id: str) -> JournalEntry:
        """Durably mark an action before an executor may be invoked."""

        with self._write_transaction() as connection:
            entry = self._load_journal_for_update(connection, journal_id)
            if entry.current_state not in {ActionState.AUTHORIZED, ActionState.RETRY_ELIGIBLE}:
                raise StateTransitionError("attempt may start only from AUTHORIZED or RETRY_ELIGIBLE")
            unresolved = connection.execute(
                """
                SELECT journal_id FROM action_journal
                WHERE task_id = ? AND journal_id != ? AND current_state IN (?, ?)
                """,
                (
                    entry.task_id, journal_id,
                    ActionState.ATTEMPT_STARTED.value, ActionState.UNCERTAIN.value,
                ),
            ).fetchall()
            if unresolved:
                raise StateTransitionError("task has another unresolved action")
            return self._transition(
                connection, entry, ActionState.ATTEMPT_STARTED, "ATTEMPT_STARTED", "RUNNING"
            )

    def record_terminal(self, journal_id: str, outcome: ActionState) -> JournalEntry:
        """Persist an explicit executor terminal result before returning it."""

        if outcome not in _TERMINAL_STATES:
            raise StateTransitionError("terminal outcome must be SUCCEEDED or FAILED")
        with self._write_transaction() as connection:
            entry = self._load_journal_for_update(connection, journal_id)
            if entry.current_state is not ActionState.ATTEMPT_STARTED:
                raise StateTransitionError("terminal outcome requires ATTEMPT_STARTED")
            return self._transition(
                connection,
                entry,
                outcome,
                "TERMINAL_SUCCEEDED" if outcome is ActionState.SUCCEEDED else "TERMINAL_FAILED",
                "ACTION_TERMINAL",
            )

    def mark_uncertain(self, journal_id: str, *, event_kind: str = "OUTCOME_UNCERTAIN") -> JournalEntry:
        """Persist that a started action lacks a trustworthy terminal result."""

        with self._write_transaction() as connection:
            entry = self._load_journal_for_update(connection, journal_id)
            if entry.current_state is not ActionState.ATTEMPT_STARTED:
                raise StateTransitionError("only ATTEMPT_STARTED may become UNCERTAIN")
            return self._transition(connection, entry, ActionState.UNCERTAIN, event_kind, "RECOVERY_REQUIRED")

    def recover_task(self, task_id: str) -> RecoveryItem:
        """Classify the latest durable fact; never invoke an executor."""

        self._validate_task_id(task_id)
        with self._write_transaction() as connection:
            unresolved = connection.execute(
                """
                SELECT * FROM action_journal
                WHERE task_id = ? AND current_state IN (?, ?)
                ORDER BY updated_at, journal_id
                """,
                (task_id, ActionState.ATTEMPT_STARTED.value, ActionState.UNCERTAIN.value),
            ).fetchall()
            if len(unresolved) > 1:
                raise StateTransitionError("multiple unresolved actions require manual recovery")
            if unresolved:
                entry = self._journal_from_row(unresolved[0])
                if entry.current_state is ActionState.ATTEMPT_STARTED:
                    entry = self._transition(
                        connection, entry, ActionState.UNCERTAIN, "RECOVERY_CLASSIFIED_UNCERTAIN", "RECOVERY_REQUIRED"
                    )
                return RecoveryItem(entry, RecoveryClassification.NEEDS_RECONCILIATION)
            row = connection.execute(
                "SELECT * FROM action_journal WHERE task_id = ? ORDER BY updated_at DESC, journal_id DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if row is None:
                return RecoveryItem(None, RecoveryClassification.NO_ATTEMPT)
            entry = self._journal_from_row(row)
            if entry.current_state in _SAFE_TO_CONTINUE_STATES:
                return RecoveryItem(entry, RecoveryClassification.SAFE_TO_CONTINUE)
            if entry.current_state is ActionState.SUCCEEDED:
                return RecoveryItem(entry, RecoveryClassification.TERMINAL_SUCCESS)
            if entry.current_state is ActionState.FAILED:
                return RecoveryItem(entry, RecoveryClassification.TERMINAL_FAILURE)
            raise StateTransitionError("journal state cannot be recovered safely")

    def reconcile(
        self, journal_id: str, observation: ReconciliationObservation
    ) -> ReconciliationResult:
        """Persist a deterministic reconciliation observation without execution."""

        if not isinstance(observation, ReconciliationObservation):
            raise StateStoreValidationError("reconciliation observation is invalid")
        with self._write_transaction() as connection:
            entry = self._load_journal_for_update(connection, journal_id)
            if entry.current_state is not ActionState.UNCERTAIN:
                raise StateTransitionError("only UNCERTAIN actions may be reconciled")
            if observation is ReconciliationObservation.CONFIRMED_SUCCEEDED:
                updated = self._transition(connection, entry, ActionState.SUCCEEDED, "RECONCILED_SUCCESS", "ACTION_TERMINAL")
            elif observation is ReconciliationObservation.CONFIRMED_FAILED:
                updated = self._transition(connection, entry, ActionState.FAILED, "RECONCILED_FAILED", "ACTION_TERMINAL")
            elif observation is ReconciliationObservation.CONFIRMED_NOT_APPLIED:
                updated = self._transition(connection, entry, ActionState.RETRY_ELIGIBLE, "RECONCILED_NOT_APPLIED", "RUNNING")
            else:
                updated = self._append_same_state_event(
                    connection, entry, "RECONCILIATION_NO_EVIDENCE", "RECOVERY_REQUIRED"
                )
            timestamp = _utcnow()
            connection.execute(
                """
                INSERT INTO reconciliation_events (
                    journal_id, observation, resulting_state, journal_sequence, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    updated.journal_id, observation.value, updated.current_state.value,
                    updated.journal_sequence, timestamp,
                ),
            )
            return ReconciliationResult(updated, observation)

    def journal_entry(self, journal_id: str) -> Optional[JournalEntry]:
        try:
            row = self._connection.execute(
                "SELECT * FROM action_journal WHERE journal_id = ?", (journal_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("action journal cannot be read") from exc
        return None if row is None else self._journal_from_row(row)

    def journal_events(self, journal_id: str) -> list[JournalEvent]:
        try:
            rows = self._connection.execute(
                "SELECT journal_id, sequence, state, event_kind, event_at FROM action_events "
                "WHERE journal_id = ? ORDER BY sequence",
                (journal_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("action journal events cannot be read") from exc
        events: list[JournalEvent] = []
        for row in rows:
            try:
                events.append(JournalEvent(
                    journal_id=self._required_text(row, "journal_id"),
                    sequence=self._required_positive_int(row, "sequence"),
                    state=ActionState(self._required_text(row, "state")),
                    event_kind=self._required_text(row, "event_kind"),
                    event_at=self._required_text(row, "event_at"),
                ))
            except (KeyError, ValueError, StateStoreError) as exc:
                raise StateStoreValidationError("action journal event record is invalid") from exc
        return events

    def checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        self._validate_task_id(task_id)
        try:
            row = self._connection.execute(
                "SELECT * FROM checkpoints WHERE task_id = ?", (task_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("checkpoint cannot be read") from exc
        if row is None:
            return None
        try:
            sequence = row["journal_sequence"]
            if sequence is not None and (not isinstance(sequence, int) or sequence < 1):
                raise StateStoreValidationError("checkpoint journal sequence is invalid")
            return Checkpoint(
                task_id=self._required_text(row, "task_id"),
                runtime_state=self._required_text(row, "runtime_state"),
                journal_id=self._optional_text(row, "journal_id"),
                journal_sequence=sequence,
                checkpoint_sequence=self._required_nonnegative_int(row, "checkpoint_sequence"),
                created_at=self._required_text(row, "created_at"),
            )
        except (KeyError, TypeError, StateStoreError) as exc:
            raise StateStoreValidationError("checkpoint record is invalid") from exc

    # -- verified task completion -----------------------------------------

    def register_task(self, task_id: str) -> None:
        """Create a task-level durable fact before any model proposal exists."""

        self._validate_task_id(task_id)
        with self._write_transaction() as connection:
            existing = connection.execute(
                "SELECT task_id FROM runtime_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is not None:
                raise StateTransitionError("durable task id already exists")
            timestamp = _utcnow()
            connection.execute(
                """
                INSERT INTO runtime_tasks (
                    task_id, runtime_state, active_journal_id, checkpoint_sequence, created_at, updated_at
                ) VALUES (?, ?, NULL, 0, ?, ?)
                """,
                (task_id, "TASK_STARTED", timestamp, timestamp),
            )
            self._write_checkpoint(connection, task_id, "TASK_STARTED", None, None, timestamp)

    def record_task_verification(
        self,
        task_id: str,
        status: VerificationStatus,
        reason_code: str,
        verifier_version: str,
        evidence: dict[str, object],
    ) -> TaskVerification:
        """Persist a trusted verifier result and the sole completion transition.

        This method is intentionally on the durable authority rather than the
        action executor. Callers must have registered the task durably; an
        accepted verifier result additionally requires a durable action
        journal, so a verifier cannot fabricate a completed task.
        """

        self._validate_task_id(task_id)
        if not isinstance(status, VerificationStatus):
            raise StateStoreValidationError("verification status is invalid")
        if not isinstance(reason_code, str) or not reason_code or len(reason_code) > 96:
            raise StateStoreValidationError("verification reason code is invalid")
        if not all(char.isupper() or char.isdigit() or char == "_" for char in reason_code):
            raise StateStoreValidationError("verification reason code is invalid")
        if not isinstance(verifier_version, str) or not verifier_version or len(verifier_version) > 64:
            raise StateStoreValidationError("verifier version is invalid")
        evidence_json = self._verification_evidence_json(evidence)
        with self._write_transaction() as connection:
            task = connection.execute(
                "SELECT task_id FROM runtime_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if task is None:
                raise StateTransitionError("verification requires an existing durable task")
            unresolved = connection.execute(
                "SELECT 1 FROM action_journal WHERE task_id = ? AND current_state IN (?, ?)",
                (task_id, ActionState.ATTEMPT_STARTED.value, ActionState.UNCERTAIN.value),
            ).fetchone()
            if unresolved is not None:
                raise StateTransitionError("verification cannot bypass unresolved action recovery")
            existing = connection.execute(
                "SELECT * FROM task_verifications WHERE task_id = ?", (task_id,)
            ).fetchone()
            if existing is not None and existing["status"] == VerificationStatus.ACCEPTED.value:
                if status is not VerificationStatus.ACCEPTED:
                    raise StateTransitionError("accepted task verification is terminal")
                return self._task_verification_from_row(existing)
            last = connection.execute(
                "SELECT MAX(verification_sequence) FROM task_verification_events WHERE task_id = ?", (task_id,)
            ).fetchone()
            sequence = (int(last[0]) if last is not None and last[0] is not None else 0) + 1
            timestamp = _utcnow()
            connection.execute(
                """
                INSERT INTO task_verification_events (
                    task_id, verification_sequence, status, reason_code, verifier_version,
                    evidence_json, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, sequence, status.value, reason_code, verifier_version, evidence_json, timestamp),
            )
            connection.execute(
                """
                INSERT INTO task_verifications (
                    task_id, status, reason_code, verifier_version, evidence_json,
                    verification_sequence, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    reason_code = excluded.reason_code,
                    verifier_version = excluded.verifier_version,
                    evidence_json = excluded.evidence_json,
                    verification_sequence = excluded.verification_sequence,
                    verified_at = excluded.verified_at
                """,
                (task_id, status.value, reason_code, verifier_version, evidence_json, sequence, timestamp),
            )
            journal = connection.execute(
                "SELECT * FROM action_journal WHERE task_id = ? ORDER BY updated_at DESC, journal_id DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if journal is None and status is VerificationStatus.ACCEPTED:
                raise StateTransitionError("accepted verification requires a durable action journal")
            entry = None if journal is None else self._journal_from_row(journal)
            runtime_state = "TASK_COMPLETED" if status is VerificationStatus.ACCEPTED else "VERIFICATION_REJECTED"
            connection.execute(
                """
                UPDATE runtime_tasks
                SET runtime_state = ?, active_journal_id = NULL, updated_at = ?
                WHERE task_id = ?
                """,
                (runtime_state, timestamp, task_id),
            )
            self._write_checkpoint(
                connection,
                task_id,
                runtime_state,
                None if entry is None else entry.journal_id,
                None if entry is None else entry.journal_sequence,
                timestamp,
            )
            return TaskVerification(
                task_id=task_id,
                status=status,
                reason_code=reason_code,
                verifier_version=verifier_version,
                evidence=json.loads(evidence_json),
                verification_sequence=sequence,
                verified_at=timestamp,
            )

    def task_verification(self, task_id: str) -> Optional[TaskVerification]:
        """Read the current verifier result without re-running any task work."""

        self._validate_task_id(task_id)
        try:
            row = self._connection.execute(
                "SELECT * FROM task_verifications WHERE task_id = ?", (task_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise StateStoreUnavailable("task verification cannot be read") from exc
        return None if row is None else self._task_verification_from_row(row)

    def schema_snapshot(self) -> dict[str, list[str]]:
        """Return table-column names for diagnostics and evidence, never values."""

        snapshot: dict[str, list[str]] = {}
        for table in (
            "schema_metadata", "authorization_replays", "runtime_tasks", "action_journal",
            "action_events", "checkpoints", "reconciliation_events", "task_verifications",
            "task_verification_events",
        ):
            try:
                snapshot[table] = [
                    str(row[1]) for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
                ]
            except sqlite3.Error as exc:
                raise StateStoreUnavailable("state schema snapshot cannot be read") from exc
        return snapshot

    @staticmethod
    def _verification_evidence_json(evidence: dict[str, object]) -> str:
        """Accept only small scalar, explicitly non-sensitive verifier facts."""

        if not isinstance(evidence, dict) or len(evidence) > 16:
            raise StateStoreValidationError("verification evidence is invalid")
        safe: dict[str, object] = {}
        forbidden = ("secret", "token", "credential", "authorization", "api_key", "password")
        for key, value in evidence.items():
            if not isinstance(key, str) or not key or len(key) > 64 or any(word in key.lower() for word in forbidden):
                raise StateStoreValidationError("verification evidence key is invalid")
            if isinstance(value, bool) or isinstance(value, int):
                safe[key] = value
            elif isinstance(value, str) and len(value) <= 256:
                safe[key] = value
            else:
                raise StateStoreValidationError("verification evidence value is invalid")
        return json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _task_verification_from_row(self, row: sqlite3.Row) -> TaskVerification:
        try:
            evidence = json.loads(self._required_text(row, "evidence_json"))
            if not isinstance(evidence, dict):
                raise ValueError("evidence is not an object")
            self._verification_evidence_json(evidence)
            return TaskVerification(
                task_id=self._required_text(row, "task_id"),
                status=VerificationStatus(self._required_text(row, "status")),
                reason_code=self._required_text(row, "reason_code"),
                verifier_version=self._required_text(row, "verifier_version"),
                evidence=evidence,
                verification_sequence=self._required_positive_int(row, "verification_sequence"),
                verified_at=self._required_text(row, "verified_at"),
            )
        except (KeyError, ValueError, TypeError, StateStoreError) as exc:
            raise StateStoreValidationError("task verification record is invalid") from exc

    # -- journal helpers ---------------------------------------------------

    def _load_journal_for_update(self, connection: sqlite3.Connection, journal_id: str) -> JournalEntry:
        row = connection.execute("SELECT * FROM action_journal WHERE journal_id = ?", (journal_id,)).fetchone()
        if row is None:
            raise StateTransitionError("action journal entry is missing")
        return self._journal_from_row(row)

    def _transition(
        self,
        connection: sqlite3.Connection,
        entry: JournalEntry,
        new_state: ActionState,
        event_kind: str,
        task_state: str,
    ) -> JournalEntry:
        allowed = {
            ActionState.AUTHORIZED: {ActionState.ATTEMPT_STARTED},
            ActionState.RETRY_ELIGIBLE: {ActionState.ATTEMPT_STARTED},
            ActionState.ATTEMPT_STARTED: {ActionState.SUCCEEDED, ActionState.FAILED, ActionState.UNCERTAIN},
            ActionState.UNCERTAIN: {ActionState.SUCCEEDED, ActionState.FAILED, ActionState.RETRY_ELIGIBLE},
        }
        if new_state not in allowed.get(entry.current_state, set()):
            raise StateTransitionError(
                f"invalid durable transition {entry.current_state.value} -> {new_state.value}"
            )
        timestamp = _utcnow()
        sequence = entry.journal_sequence + 1
        connection.execute(
            """
            UPDATE action_journal
            SET current_state = ?, journal_sequence = ?, updated_at = ?
            WHERE journal_id = ?
            """,
            (new_state.value, sequence, timestamp, entry.journal_id),
        )
        self._append_event(connection, entry.journal_id, sequence, new_state, event_kind, timestamp)
        active = None if new_state in _TERMINAL_STATES else entry.journal_id
        connection.execute(
            """
            UPDATE runtime_tasks
            SET runtime_state = ?, active_journal_id = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (task_state, active, timestamp, entry.task_id),
        )
        self._write_checkpoint(connection, entry.task_id, task_state, entry.journal_id, sequence, timestamp)
        return JournalEntry(
            journal_id=entry.journal_id,
            task_id=entry.task_id,
            action_identity=entry.action_identity,
            idempotency_key=entry.idempotency_key,
            principal_id=entry.principal_id,
            request_fingerprint=entry.request_fingerprint,
            security_context_fingerprint=entry.security_context_fingerprint,
            authorization_decision=entry.authorization_decision,
            current_state=new_state,
            journal_sequence=sequence,
            created_at=entry.created_at,
            updated_at=timestamp,
        )

    def _append_same_state_event(
        self,
        connection: sqlite3.Connection,
        entry: JournalEntry,
        event_kind: str,
        task_state: str,
    ) -> JournalEntry:
        timestamp = _utcnow()
        sequence = entry.journal_sequence + 1
        connection.execute(
            "UPDATE action_journal SET journal_sequence = ?, updated_at = ? WHERE journal_id = ?",
            (sequence, timestamp, entry.journal_id),
        )
        self._append_event(connection, entry.journal_id, sequence, entry.current_state, event_kind, timestamp)
        connection.execute(
            "UPDATE runtime_tasks SET runtime_state = ?, updated_at = ? WHERE task_id = ?",
            (task_state, timestamp, entry.task_id),
        )
        self._write_checkpoint(connection, entry.task_id, task_state, entry.journal_id, sequence, timestamp)
        return JournalEntry(
            journal_id=entry.journal_id,
            task_id=entry.task_id,
            action_identity=entry.action_identity,
            idempotency_key=entry.idempotency_key,
            principal_id=entry.principal_id,
            request_fingerprint=entry.request_fingerprint,
            security_context_fingerprint=entry.security_context_fingerprint,
            authorization_decision=entry.authorization_decision,
            current_state=entry.current_state,
            journal_sequence=sequence,
            created_at=entry.created_at,
            updated_at=timestamp,
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        journal_id: str,
        sequence: int,
        state: ActionState,
        event_kind: str,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO action_events (journal_id, sequence, state, event_kind, event_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (journal_id, sequence, state.value, event_kind, timestamp),
        )

    @staticmethod
    def _write_checkpoint(
        connection: sqlite3.Connection,
        task_id: str,
        runtime_state: str,
        journal_id: Optional[str],
        journal_sequence: Optional[int],
        timestamp: str,
    ) -> None:
        previous = connection.execute(
            "SELECT checkpoint_sequence FROM checkpoints WHERE task_id = ?", (task_id,)
        ).fetchone()
        checkpoint_sequence = (int(previous[0]) if previous is not None else 0) + 1
        connection.execute(
            """
            INSERT INTO checkpoints (
                task_id, runtime_state, journal_id, journal_sequence, checkpoint_sequence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                runtime_state = excluded.runtime_state,
                journal_id = excluded.journal_id,
                journal_sequence = excluded.journal_sequence,
                checkpoint_sequence = excluded.checkpoint_sequence,
                created_at = excluded.created_at
            """,
            (task_id, runtime_state, journal_id, journal_sequence, checkpoint_sequence, timestamp),
        )
        connection.execute(
            "UPDATE runtime_tasks SET checkpoint_sequence = ? WHERE task_id = ?",
            (checkpoint_sequence, task_id),
        )

    def _journal_from_row(self, row: sqlite3.Row) -> JournalEntry:
        try:
            entry = JournalEntry(
                journal_id=self._required_text(row, "journal_id"),
                task_id=self._required_text(row, "task_id"),
                action_identity=self._required_text(row, "action_identity"),
                idempotency_key=self._required_text(row, "idempotency_key"),
                principal_id=self._required_text(row, "principal_id"),
                request_fingerprint=self._required_text(row, "request_fingerprint"),
                security_context_fingerprint=self._required_text(row, "security_context_fingerprint"),
                authorization_decision=self._required_text(row, "authorization_decision"),
                current_state=ActionState(self._required_text(row, "current_state")),
                journal_sequence=self._required_positive_int(row, "journal_sequence"),
                created_at=self._required_text(row, "created_at"),
                updated_at=self._required_text(row, "updated_at"),
            )
        except (KeyError, ValueError, StateStoreError) as exc:
            raise StateStoreValidationError("action journal record is invalid") from exc
        if entry.authorization_decision != "allow":
            raise StateStoreValidationError("action journal authorization is invalid")
        return entry

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
            raise StateStoreValidationError("task id is invalid")

    @staticmethod
    def _required_text(row: sqlite3.Row, name: str) -> str:
        value = row[name]
        if not isinstance(value, str) or not value:
            raise StateStoreValidationError(f"durable field {name} is invalid")
        return value

    @staticmethod
    def _optional_text(row: sqlite3.Row, name: str) -> Optional[str]:
        value = row[name]
        if value is None:
            return None
        if not isinstance(value, str):
            raise StateStoreValidationError(f"durable field {name} is invalid")
        return value

    @staticmethod
    def _required_positive_int(row: sqlite3.Row, name: str) -> int:
        value = row[name]
        if not isinstance(value, int) or value < 1:
            raise StateStoreValidationError(f"durable field {name} is invalid")
        return value

    @staticmethod
    def _required_nonnegative_int(row: sqlite3.Row, name: str) -> int:
        value = row[name]
        if not isinstance(value, int) or value < 0:
            raise StateStoreValidationError(f"durable field {name} is invalid")
        return value
