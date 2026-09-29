# Astron Phase 3: Verified Completion Contract

## Core rule

```text
MODEL_SAYS_DONE != TASK_COMPLETED
VERIFIER_PASS == the only Phase 3 completion authority
```

The native agent loop may stop proposing actions when the model reports done,
when its bounded step budget is exhausted, or when an action fails. None of
those states is success. A trusted deterministic verifier runs after the loop
and owns the only transition to `TASK_COMPLETED`.

## Verifier inputs and checks

The maintenance fixture has a fixed baseline tree hash and a task contract.
The verifier receives the copied workspace and the persisted task identity;
it does not receive the model's self-assessment as an input. It evaluates:

1. the workspace is still within its copied fixture root;
2. changed paths are within the fixture's explicitly permitted maintenance
   scope and no fixture test or verifier input was altered;
3. the required artifact exists, is valid JSON, and has the bounded expected
   shape;
4. the deterministic fixture test suite passes through the trusted bounded
   pytest contract; and
5. the final tree/hash facts are internally consistent.

It records `ACCEPTED` or `REJECTED`, a stable reason code, a verifier version,
and redacted deterministic evidence in the Phase 2 SQLite authority. A
verification event is append-only; the current task verification snapshot is
durable. `TASK_COMPLETED` may be written only by a successful verifier
recording transaction, never by an action executor or agent-loop branch.

## Non-success states

| Situation | Completion result |
| --- | --- |
| model claims completion before fixing the fixture | `REJECTED` |
| model does no actions | `REJECTED` |
| action denied, fails, times out, or becomes uncertain | `REJECTED` / recovery required |
| verifier test fails | `REJECTED` |
| required artifact is absent or malformed | `REJECTED` |
| verifier passes all fixed checks | `ACCEPTED`, durable `TASK_COMPLETED` |

The verifier does not prove a general property of an arbitrary repository. It
proves only the declared fixture contract on one fresh copied workspace.
