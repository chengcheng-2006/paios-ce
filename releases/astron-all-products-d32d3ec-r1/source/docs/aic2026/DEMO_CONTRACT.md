# Astron Phase 3: Repository-Maintenance Demo Contract

## Demonstration task

Phase 3 supplies one deterministic repository-maintenance fixture. Its source
tree deliberately begins with a failing configuration test. Each run uses a
fresh copy, so a previous successful result cannot repair or mask the next
baseline. The task asks the agent to diagnose the failing configuration, make
the smallest permitted source correction, run the allowed tests, and write a
bounded structured change summary.

The task prompt names the goal and permitted workflow and exposes the verified
completion-artifact schema from the same typed contract used by the verifier.
It does not embed the expected source edit, expected final literal, final diff,
hidden tests, or verifier shortcuts. Schema is visible; the answer remains in
the trusted fixture and verifier implementation.

For a live-certification run, the trusted `maintenance-baseline` CLI command
creates that same fresh copy and invokes only `test.run_pytest_bounded` before
any credential is requested. Its expected test failure is recorded as
`FAIL_AS_EXPECTED`; a pass, timeout, configuration error, or reconciliation
state stops the run before a provider request. The subsequent live task may
reopen only a fixture whose trusted baseline digest still matches, apart from
pytest cache directories.

## Agent-loop limits

| Limit | Phase 3 contract |
| --- | --- |
| maximum proposals | six model turns per task |
| maximum actions | fixed small per-task limit |
| model output | provider-configured token and byte bound |
| tool output | per-tool bounded result payload |
| task time | one fixed overall deadline |
| test time | one fixed child-process deadline |
| agent contract | `AIC2026_READ_BATCH_VERIFIED_ARTIFACT_V4` |
| admitted model tool calls per turn | zero; one bounded call; or two to four allowlisted reads |
| read-only batch allowlist | `workspace.list_files`, `workspace.read_text` only |
| execution order | strictly sequential; no parallel tool execution |
| completion schema | trusted `maintenance_completion.v1` registry entry |

The Agent instruction is explicit behavioral guidance: a turn may propose up
to four reads only when every call is on the frozen read-only batch allowlist.
Any other operation must be the sole call in its turn. The instruction does
not make an LLM prompt a security boundary. Native runtime admission validates
the entire multi-call operation set before any call executes, rejecting mixed,
unknown, or over-limit batches with `INVALID_MODEL_OUTPUT` and zero execution.

Every admitted read is a separate action. Astron executes the calls in provider
order through the existing Permission Engine and durable runtime, forms one
terminal result per provider call ID, and sends the next model request only
after all results exist. A failed path or permission check does not expand the
workspace scope and does not authorize a mutating operation.

The loop records each action outcome in its transient prompt context before
the next model turn, but stores no secret, raw provider payload, or tool
argument in SQLite. Safe CLI evidence can contain only response cardinality,
bounded syntactically safe operation names, the batch classification, and
content-free completion-contract metadata. On restart, each action's durable
journal and the verifier record remain authoritative; model context is not
reconstructed as proof. Read batching does not create a strict exactly-once
guarantee.

## Verified completion artifact

`paios_ce.maintenance_artifact.MAINTENANCE_COMPLETION_ARTIFACT_CONTRACT`
is the authoritative Agent/Verifier contract source. It fixes the path to
`.astron-artifacts/change_summary.json`, derives the Agent-facing instructions
and schema, validates the runtime-bound task ID, and supplies the verifier's
semantic check. The required keys are `task_id`, `changed_files`, and
`summary`; types, relative-path meaning, length bounds, and the current
extra-key policy come from that same typed object.

The optional `schema_id=maintenance_completion.v1` argument to `validate.json`
selects only that trusted registry entry. It cannot name a schema file or an
arbitrary schema. Without `schema_id`, `validate.json` checks syntax only. A
semantic PASS is evidence for the model's next decision, not completion;
`MaintenanceVerifier` independently checks the artifact and remains the sole
authority that can persist `TASK_COMPLETED`.

## Modes and evidence language

`mock` mode is deterministic and offline. It proves the integrated
proposal-to-verifier chain, not a real AI/provider interaction.

`live` mode is an explicit separate path. It requires the documented live
provider configuration and named environment credential. If that credential
is not deliberately supplied, live mode is blocked without a fallback to a
different provider or a fake success.

Evidence distinguishes these outcomes:

| Record | Meaning |
| --- | --- |
| `OFFLINE_E2E=PASS` | deterministic mock completed a fresh fixture and verifier accepted it |
| `REAL_E2E=PASS` | named live provider completed a separate fresh fixture and verifier accepted it |
| `BLOCKED_EXTERNAL_CREDENTIAL` | live preflight/task was not eligible because no named credential was supplied |

An offline PASS never upgrades a blocked live provider gate. No Phase 4
capability is admitted by this demo.
