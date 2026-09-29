# Operations

What exists on disk at runtime, what to read when something goes wrong, and what
you may and may not do to a stuck task.

## Normal operation

There is no daemon. A run is one process: it opens a durable SQLite store, does
its bounded work, and exits. `astron --help` lists the seven entry points; exit
codes are stable and machine-readable.

```text
0 success   2 usage   3 configuration/validation   4 denied   5 blocked   6 internal
```

`4` and `5` are **not** failures of the runtime — they are the runtime working as
intended. Alert on `6` and on repeated `3`; treat `4`/`5` as expected traffic from
any model that is exploring its tool surface.

## Where state lives

| Artifact | Path | Notes |
| --- | --- | --- |
| Durable state | whatever you pass as `--state-db`, or the `state:` block in a private config | one SQLite file plus `-wal`/`-shm` sidecars; created `0o600`, re-verified on open |
| Agent workspace | `--workspace` (fixture copy) | Astron copies the trusted fixture; it does not edit the source tree |
| Completion artifacts | `<workspace>/.astron-artifacts/` | mode `0o700`, writes are atomic (`tempfile` + `os.replace` + `fsync`) |
| Terminal session logs | `<workspace parent>/.astron-terminal-logs/`, including `action-journal.jsonl` | only when a terminal-capable runtime is composed |
| Audit events | **in memory unless you pass a stream** | `RedactedAuditLogger` defaults to `io.StringIO()` (`audit/logger.py:48-51`); `astron run-task` prints the event in its JSON result |
| Provider payloads | nowhere | raw requests/responses are not persisted; only bounded redacted diagnostics come back in the result |

The last row is an operational consequence worth stating: **Astron does not ship
an audit-log writer.** To keep an audit trail you pass your own stream:

```python
from pathlib import Path
from paios_ce.audit import RedactedAuditLogger

sink = Path("/var/log/astron/audit.jsonl").open("a", encoding="utf-8")
audit = RedactedAuditLogger(stream=sink)
```

## Reading the durable facts

```bash
sqlite3 state.sqlite '.tables'
sqlite3 state.sqlite 'select task_id, runtime_state, active_journal_id from runtime_tasks'
sqlite3 state.sqlite 'select journal_id, current_state, journal_sequence, updated_at from action_journal order by updated_at'
sqlite3 state.sqlite 'select sequence, state, event_kind from action_events where journal_id=? order by sequence'
sqlite3 state.sqlite 'select observation, resulting_state from reconciliation_events'
sqlite3 state.sqlite 'select task_id, status, reason_code, verifier_version from task_verifications'
```

`action_events` is append-only, so this is your chronology: who was authorized,
when an attempt started, whether anything was ever settled.
`store.schema_snapshot()` (Python) prints the same picture as a dict.

The state file is deliberately **not** a place to write. There is no supported
SQL edit path; wrong rows make the store refuse the task.

## Task interrupted — the decision table

Open the store in a fresh process and call `recover_task(task_id)`. It only reads
(and, for one case, classifies). It never executes.

| Classification | Meaning | What you do |
| --- | --- | --- |
| `NO_ATTEMPT` | nothing was journaled | safe to run the action normally |
| `SAFE_TO_CONTINUE` | authorized, attempt not started | re-invoke `execute` for that action; nothing has happened yet |
| `TERMINAL_SUCCESS` / `TERMINAL_FAILURE` | settled fact | do **not** re-run; move on or report |
| `NEEDS_RECONCILIATION` | attempt started, no terminal outcome | the action's effect is unknown — go to reconciliation |

A task with more than one unresolved action raises
`StateTransitionError("multiple unresolved actions require manual recovery")`.
That is a stop-and-look condition, not a retry condition.

## UNCERTAIN, in one paragraph

`UNCERTAIN` means: an attempt was recorded, and the process cannot prove what the
world looks like now. It is reached when the executor raises after the durable
attempt boundary, when a terminal outcome could not be persisted, or when
recovery finds `ATTEMPT_STARTED` with nothing after it. Astron will not retry it
automatically, because for an external effect a retry can be worse than a stall.

Clearing it requires a trusted `Reconciler` for **that action**:

| Observation | Resulting state | Executes anything? |
| --- | --- | --- |
| `CONFIRMED_SUCCEEDED` | `SUCCEEDED` | no |
| `CONFIRMED_FAILED` | `FAILED` | no |
| `CONFIRMED_NOT_APPLIED` | `RETRY_ELIGIBLE` (a later explicit `execute` may run) | no |
| `NO_EVIDENCE` | stays `UNCERTAIN`, one event appended | no |

If you cannot build an observer for an action type, that action type should not be
added. See `examples/demos/03_crash_and_reconcile.py` for a complete worked case
and `docs/aic2026/RECOVERY_SEMANTICS.md` for the contract text.

## Backing up and keeping state private

```bash
sqlite3 state.sqlite ".backup state.sqlite.bak"   # consistent snapshot
cp -a state.sqlite state.sqlite.bak               # only with no writer active
```

The store keeps WAL and `synchronous=FULL` on purpose and refuses to open if
SQLite will not grant them, so a copy taken while a process is writing is not a
consistent backup. Stop the writer first.

Check the mode before moving anything, especially on shared machines:

```bash
ls -l state.sqlite state.sqlite-wal 2>/dev/null    # expect -rw-------
```

A world- or group-writable state file makes Astron fail closed at open
(`PrivateFileSecurityError`). The fix is yours to make deliberately
(`chmod 600`), not the runtime's to apply silently.

## Logs to read, in order

1. the JSON the CLI printed (`decision`, `error_code`, `execution_attempted`,
   `status`, `verifier`, `provider_error`);
2. `action_events` for the task;
3. `.astron-terminal-logs/action-journal.jsonl` if terminal tools were used —
   output there is capped and secret-redacted;
4. `provider_diagnostics` for transport problems — codes, never payloads.

`audit/redact.py` strips secret-shaped keys/values and refuses events it cannot
prove are clean (`RedactionNotGuaranteedError`, and a
`AUDIT_WRITE_FAILED`-style fallback event instead of the offending one). If you
see an audit line missing a field you expected, assume redaction, not corruption.

## Stopping work

* `Ctrl-C` → the CLI prints `{"status": "interrupted"}` and exits 2. Already
  journaled facts stay as they are; nothing is rolled back (`rollback_supported`
  is `False` for every operation in this snapshot).
* A hung bounded pytest run is killed at `--pytest-timeout` (1-60 s, default 15)
  with `terminate()` then `kill()`, and reports `{"status": "TIMEOUT"}`.
* Terminal sessions: `terminal_signal` accepts **only** `SIGINT`, sent to the
  process group. `terminal_close` and `shutdown()` escalate to `SIGTERM` for the
  group. Always call `tools.shutdown()` in a `finally` —
  `cli/main.py:115-118` is the model. Shutdown is a lifecycle boundary, not a
  success claim.

## What this package does not give you

No service manager, no systemd unit, no container, no health endpoint, no metrics
exporter, no rotation, no alerting, and no `astron state reset`. Nothing in here
is a production control plane; `SUPPORT_MATRIX.md` labels the modules
`EXPERIMENTAL` or `Scaffold` for exactly this reason.

If you need "clear everything and start again", the honest procedure is: stop the
writer, copy the SQLite file aside for forensics, then point `--state-db` at a new
path. Deleting state destroys the only evidence of what an uncertain action did,
which is the thing the runtime exists to keep.
