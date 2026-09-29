# Astron Authorization Idempotency and Replay Semantics

> **Phase 2 status update.** This document preserves the Phase 1 identity
> contract below.  When `PermissionEngine` is explicitly configured with a
> Phase 2 `SQLiteDurableStateStore`, keyed authorization records are durable
> across process restart and cross-process first authorization is serialized.
> The durable store does not make an authorization result proof of execution;
> execution facts remain in the separate Action Journal described in
> [DURABLE_RUNTIME.md](DURABLE_RUNTIME.md).

## Scope and non-goals

Phase 1 defined **in-memory authorization replay**.  Phase 2 retains that
behavior for engines with no durable store, and adds durable replay for an
engine configured with the explicit local state authority.  Neither mode
records external side effects, completion, or outcomes in the authorization
record itself.

```text
AUTHORIZATION_REPLAY=SUPPORTED
DURABLE_AUTHORIZATION_REPLAY=SUPPORTED_WHEN_SQLITE_STORE_CONFIGURED
PROCESS_RESTART_AUTHORIZATION_REPLAY=SUPPORTED_WHEN_SQLITE_STORE_CONFIGURED
DURABLE_ACTION_REPLAY=SUPPORTED_BY_SEPARATE_ACTION_JOURNAL
```

Neither phase claims exactly-once side effects.  Phase 2 adds action-journal
durability, restart recovery, and uncertain-outcome reconciliation under its
separate recovery contract; it does not turn a cached authorization result
into execution evidence.

## Terms and trust boundary

An `idempotency_key` is a caller-supplied stable label for one logical action
intent. It is not an authorization token, a permission, proof that an action
executed, proof of success, a checkpoint, or an artifact identity.

`ActionRequest` remains an untrusted action payload. In particular, ordinary
parameters named `principal`, `principal_id`, `actor`, `user`, or similar have
no authorization meaning. The trusted runtime supplies a separate immutable
principal context to `PermissionEngine.authorize`; the engine's configured
principal is the backward-compatible default when that context is omitted.

The local `run-task --principal-id` adapter supplies that runtime-side context
outside of the action JSON. It must be connected to an authenticated caller by
any future multi-user transport; an ActionRequest field or parameter never
overrides it.

## Canonical authorization identity

For a keyed request, the engine constructs an in-memory authorization identity:

```text
idempotency_key
trusted_principal_id
request_fingerprint
security_context_fingerprint
```

`request_fingerprint` is SHA-256 of UTF-8 canonical JSON for the security
relevant request representation plus the trusted principal. The representation
includes the protocol version, worker type, operation, normalized parameters,
required capabilities, filesystem/network/process scopes, timeout,
rollback/approval flags, and safe presence-only treatment for `admin_token`.
It intentionally excludes `action_id` (a submission identifier) and logging
metadata such as trace IDs when they do not otherwise occur in parameters.

`security_context_fingerprint` is SHA-256 of canonical JSON for the existing
authorization inputs: capability grant, owner allowlist, scope grant,
high-risk-confirmation setting, and static risk-policy table. It prevents a
cached ALLOW from silently surviving a mutation to a currently real decision
input. No speculative RBAC or policy-version system is introduced.

Canonical JSON uses typed normalization, UTF-8, sorted object keys, deterministic
separators, and SHA-256. It never uses `hash()`, `str(dict)`, `repr()`, memory
addresses, or insertion-order-dependent output. Mapping keys are sorted; list
order is preserved; sets are deterministically sorted; Pydantic/dataclass
values have an explicit type marker; finite numbers are normalized; and
non-finite or unknown mutable objects fail closed rather than being rendered.

`SecretRef` is represented only by its stable safe reference identity
(`backend_id` plus `redact()` label). The fingerprint path never calls
`SecretRef.resolve()`, never reads a `SecretValue`, and never includes a secret
value, prefix, or secret-derived hash. A supplied `SecretValue` is rejected
fail closed.

## Replay algorithm

```text
request + trusted principal context
  -> canonical authorization identity
  -> idempotency key absent?
       -> normal authorization, with action-id duplicate protection
  -> key not recorded?
       -> normal authorization; atomically store complete result snapshot
  -> key recorded and all identity components equal?
       -> return original result snapshot with REPLAYED=true
  -> key recorded but any component differs?
       -> BLOCKED, E_IDEMPOTENCY_KEY_REUSE_MISMATCH; retain original record
  -> record malformed or canonicalization unavailable?
       -> BLOCKED fail closed; never overwrite a prior record
```

The stored replay record retains the idempotency key, trusted principal,
request/security-context fingerprints, and the complete original authorization
result (decision, class, risk, reason, hard-block flag, confirmation kind, and
error code). Exact replay therefore preserves `ALLOW`, `DENY`, `BLOCKED`, or
`CONFIRMATION_REQUIRED` rather than reconstructing an allow result.

`ActionRequest.idempotency_key` is optional in Phase 1 for the engine's
pre-existing non-idempotent path. Existing keyed payloads remain valid. A
keyless request is never cached and remains subject to action-id duplicate
protection.

## Fail-closed behavior and concurrency

An idempotency identity mismatch returns `BLOCKED` with stable error code
`E_IDEMPOTENCY_KEY_REUSE_MISMATCH`; it does not re-evaluate, replace, delete,
or relax the original record. A malformed replay record returns
`E_IDEMPOTENCY_REPLAY_RECORD_INVALID`. A canonicalization failure returns
`E_IDEMPOTENCY_FINGERPRINT_INVALID`. None authorizes execution.

`PermissionEngine` is a public in-process library object and can be reached
from concurrent callers. Its lookup, identity comparison, evaluation, and
record-store sequence is therefore protected by a process-local re-entrant
lock when operating in-memory.  With an explicit `SQLiteDurableStateStore`,
keyed authorization instead uses a short `BEGIN IMMEDIATE` transaction and a
unique idempotency-key record: two processes cannot both create divergent
first records.  Store lock, corruption, unsupported schema, or malformed
record errors return a stable fail-closed state error rather than falling back
to in-memory authorization.

## Security guarantee boundary

Phase 1 guarantees that an exact authorization replay preserves the original
decision; a key cannot silently cross changed parameters, action/security
scope, trusted principals, or current authorization context; unknown actions
remain deny-by-default; and replay conflicts fail closed.

Phase 1 did **not** provide persistent replay records, durable action outcome
storage, process-restart replay, crash recovery, or uncertain-action
reconciliation.  Phase 2 adds those bounded runtime facts as documented in
`DURABLE_RUNTIME.md` and `RECOVERY_SEMANTICS.md`.  Astron still does **not**
provide exactly-once real side effects for arbitrary external systems, artifact
verification, or verified task completion.
