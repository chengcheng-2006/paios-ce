# Astron Phase 2: Recovery and Reconciliation Semantics

## Principle

```text
unknown != not executed
uncertain != retry eligible
```

Recovery is derived from durable journal facts only.  A new process first
opens and validates the state store, loads the task checkpoint, then loads the
latest journal truth.  It does not infer an execution result from a missing
in-memory response.

## Action state machine

`RECORDED` is retained as the first append-only journal event; a newly
prepared permitted action's current state becomes `AUTHORIZED` in the same
transaction.  `RETRY_ELIGIBLE` is an explicit, persisted result of a trusted
reconciler, never an implicit recovery default.

```text
RECORDED -> AUTHORIZED -> ATTEMPT_STARTED -> SUCCEEDED
                                      |  \-> FAILED
                                      \----> UNCERTAIN

UNCERTAIN -- confirmed_succeeded --> SUCCEEDED
UNCERTAIN -- confirmed_failed ----> FAILED
UNCERTAIN -- confirmed_not_applied -> RETRY_ELIGIBLE
RETRY_ELIGIBLE --------------------> ATTEMPT_STARTED  (only on a later explicit call)
```

An unknown reconciliation observation leaves the current state `UNCERTAIN`
and appends an event.  `SUCCEEDED` and `FAILED` are terminal for ordinary
execution and replay paths.  They cannot move back to `AUTHORIZED`,
`ATTEMPT_STARTED`, or another terminal state.  A state update outside the
listed transitions fails closed and preserves history.

## Restart classification

| Latest durable journal state | Recovery classification | Automatic executor invocation |
| --- | --- | --- |
| no journal | `NO_ATTEMPT` | none; no action is fabricated |
| `RECORDED` / `AUTHORIZED` / `RETRY_ELIGIBLE` | `SAFE_TO_CONTINUE` | no; a caller must explicitly continue |
| `ATTEMPT_STARTED` without a terminal event | `UNCERTAIN` and `NEEDS_RECONCILIATION` | never |
| `UNCERTAIN` | `NEEDS_RECONCILIATION` | never |
| `SUCCEEDED` | `TERMINAL_SUCCESS` | never |
| `FAILED` | `TERMINAL_FAILURE` | never |

The classification of `ATTEMPT_STARTED` is intentionally conservative even
if a crash occurred before the executor instruction actually ran.  The durable
record proves only that an attempt might have started.

## Reconciliation contract

A reconciler is a deterministic, trusted, action-type-specific component. It
observes external facts; it never reruns the action.  The Phase 2 interface
returns one of:

| Observation | Persisted transition | Meaning |
| --- | --- | --- |
| `CONFIRMED_SUCCEEDED` | `UNCERTAIN -> SUCCEEDED` | trustworthy evidence says the prior side effect occurred |
| `CONFIRMED_FAILED` | `UNCERTAIN -> FAILED` | trustworthy evidence says it did not succeed |
| `CONFIRMED_NOT_APPLIED` | `UNCERTAIN -> RETRY_ELIGIBLE` | trustworthy evidence says the effect definitely did not occur |
| `NO_EVIDENCE` | remains `UNCERTAIN` | evidence is absent or inconclusive |

Every reconciliation observation gets an append-only reconciliation event.
`CONFIRMED_NOT_APPLIED` does not automatically execute the action.  It only
creates a durable eligibility state that a later explicit runtime call may
use.  An LLM assessment is not a reconciliation observation and has no power
to create `RETRY_ELIGIBLE`.

## Crash-window consequences

| Window | Durable facts at exit | Recovery result |
| --- | --- | --- |
| before journal intent commit | no action journal | `NO_ATTEMPT` |
| authorized journal committed; attempt not committed | `AUTHORIZED` | `SAFE_TO_CONTINUE` |
| attempt committed; no terminal result | `ATTEMPT_STARTED` | transition to `UNCERTAIN`; reconciliation required |
| side effect happened; success not committed | `ATTEMPT_STARTED` | `UNCERTAIN`; reconcile, do not execute again |
| success committed; response not returned | `SUCCEEDED` | terminal success; do not execute again |
| failure committed; response not returned | `FAILED` | terminal failure; do not invent success |

The final three rows are explicitly exercised with independently restarted
processes and a safe deterministic test ledger.  They demonstrate prevention
of blind duplicate execution in the tested windows only; they do not provide
a strict exactly-once guarantee for arbitrary external systems.
