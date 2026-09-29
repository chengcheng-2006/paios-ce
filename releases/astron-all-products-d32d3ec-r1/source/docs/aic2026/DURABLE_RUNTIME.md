# Astron Phase 2: Durable Runtime Design

## Scope and authority boundary

Phase 2 adds a local, versioned SQLite state authority for durable
authorization records and action-recovery facts.  It does **not** add a live
provider, a bounded developer tool, artifact verification, task-completion
verification, or a claim of exactly-once execution for arbitrary external
systems.

```text
STRICT_EXACTLY_ONCE_GUARANTEE=NO
VERIFIED_TASK_COMPLETION=NOT_IMPLEMENTED
```

SQLite is not a cache and a durable authorization record is not proof that an
action executed.  The durable action journal, rather than process memory or a
checkpoint, is authoritative for an action's execution facts.

## Durable logical entities

Schema version 1 was the Phase 2 baseline. The current Phase 3 schema version
is 2 and preserves its v1 history while adding verifier-only task facts:

| Entity | Durable facts | Authority |
| --- | --- | --- |
| `schema_metadata` | schema version | validates whether history can be read safely |
| `authorization_replays` | key, trusted principal, request/security fingerprints, full redacted authorization decision | exact authorization replay across a restart |
| `runtime_tasks` | runtime-only task recovery state | task-level recovery coordination; not verified completion |
| `action_journal` | stable action identity, authorization linkage, current action state, journal sequence | current execution/recovery truth |
| `action_events` | append-only state/event history | audit history for each journal transition |
| `checkpoints` | task state plus latest journal sequence at a durable boundary | safe task-progress restoration only |
| `reconciliation_events` | deterministic reconciliation observation and resulting state | explains how an uncertain action was resolved |
| `task_verifications` | current redacted deterministic verifier result | the only authority for `TASK_COMPLETED` |
| `task_verification_events` | append-only verifier decision history | explains acceptance/rejection transitions |

The state store records no request parameter payload, executor payload,
resolved secret, raw token, credential, or `SecretValue`.  The only action
identity material is Phase 1's idempotency key, trusted principal, and
canonical SHA-256 request/security-context fingerprints.  An action journal
entry obtains its stable `action_identity` from those four values.

## SQLite configuration and file handling

The standard-library `sqlite3` module is the only database dependency.  A
newly created state database is created with owner-only `0600` permissions on
macOS.  Opening an existing database that is group- or world-readable or
writable fails closed; the store never changes its permissions implicitly.

The store explicitly sets and verifies:

```text
foreign_keys=ON
journal_mode=WAL
synchronous=FULL
busy_timeout=1000 ms
security-critical transaction=BEGIN IMMEDIATE ... COMMIT
```

WAL is selected to permit a reader to observe a prior durable snapshot while
a short writer transaction serializes first authorization and journal
transitions.  `FULL` is deliberately chosen over a weaker performance setting.
This configuration improves local durability but does not claim immunity to
all storage, hardware, or external-system failures.

## Versioning, migration, and failed-closed behavior

`schema_metadata.schema_version` is a required, explicit contract. A fresh
empty DB is initialized through v1 then v2. Version 0 is migrated
deterministically through v1 to v2; a v1 DB receives the additive v2 verifier
tables in a transaction. A version newer than the runtime, a malformed version
marker,
an incomplete schema, an unreadable/corrupt DB, or a lock that outlives the
bounded timeout produces `STATE_STORE_UNAVAILABLE` / a typed state-store
error.  It never deletes, recreates, or replaces the database.

When durable state is configured, authorization and recovery paths do not
fall back to an in-memory record after a store error.  That is especially
important because otherwise a missing history could be mistaken for an action
that never started.

## Authorization replay

`PermissionEngine` continues to produce the Phase 1 canonical
`AuthorizationIdentity`.  With the durable store attached, keyed
authorization is a `BEGIN IMMEDIATE` transaction:

```text
lookup idempotency key
  -> no record: evaluate and persist a complete decision snapshot, then commit
  -> same principal + request fingerprint + security-context fingerprint:
       restore the stored decision as REPLAYED
  -> any identity difference: retain original record and BLOCK
       E_IDEMPOTENCY_KEY_REUSE_MISMATCH
```

This transaction is intentionally narrow and contains no side effect.  Its
unique idempotency-key constraint and writer serialization give two processes
one authoritative first record.  The process-local Phase 1 map remains a
compatibility optimization only when no durable store is configured; a durable
store is always consulted for a configured durable runtime.

## Durable runtime execution boundary

A `DurableActionRuntime` is deliberately separate from the existing minimal
orchestrator and mock worker.  It accepts an already-known test or future
trusted executor, but it does not expose an arbitrary executor to a model or
CLI.  For an authorization that allows a potential side effect, its order is:

```text
authorize and durably store replay decision
  -> create journal record and checkpoint (COMMIT)
  -> record ATTEMPT_STARTED and checkpoint (COMMIT)
  -> invoke executor
  -> record SUCCEEDED or FAILED and checkpoint (COMMIT)
  -> return to caller
```

If the executor raises after the attempt boundary, the runtime cannot prove
that no side effect happened, so it records `UNCERTAIN`; it does not convert
the exception into `FAILED` or retry it.  A terminal `FAILED` result is only
recorded when the executor returns an explicit durable failure outcome.

`runtime_tasks`, `action_journal`, append-only `action_events`, and the
corresponding checkpoint are written in the same transaction at each durable
boundary.  The runtime permits at most one unresolved action per task.  A
database with multiple unresolved actions for one task is a recovery error,
not an invitation to guess an ordering.

## Checkpoint authority

A checkpoint contains the task's runtime-only state, the action journal
reference, the journal sequence, a checkpoint sequence, and creation time. It
is not a Python-object pickle or chat-history dump.  If it conflicts with the
journal, the journal wins.  In particular, a checkpoint that says `RUNNING`
cannot authorize work when the latest journal truth is `UNCERTAIN`.

Phase 2 evidence was collected before this schema's Phase 3 extension and did
not name a task `TASK_COMPLETED`. In schema v2, only
`record_task_verification(ACCEPTED, ...)` may write that state and its
checkpoint; a successful action journal still proves neither artifact
acceptance nor verified completion.

## Real-process test boundary

The production runtime contains no model-controlled crash switch.  The test
suite uses a separate child-process fixture, a temporary SQLite DB, and a
deterministic append-once event ledger.  Crash points are induced either by a
test executor exiting its owned child process or by a test-only store subclass
that exits immediately after a real commit.  The fixture is not a production
bounded tool.
