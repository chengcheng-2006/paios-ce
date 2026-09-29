# Source map

Every path below exists in this package. Line numbers are from snapshot
`d32d3ec`. The short answers first, then the module-by-module map.

## The eight questions

| Question | Answer |
| --- | --- |
| Where does it start? | `src/paios_ce/cli/main.py:601` `main()` → `build_parser()` at `:521`. Console scripts `astron` / `paios-ce` in `pyproject.toml`. As a library: construct provider + `FixtureWorkspace` + `SQLiteDurableStateStore` + `BoundedToolRuntime` + `NativeAgent` and call `run(task_id)` (`cli/main.py:95-118` is that wiring in production form). |
| Where is the model request? | `src/paios_ce/agent/native.py:171` `self._provider.tool_call(ChatRequest(...))`. Implementations: `providers/openai_compatible.py:206` (`tool_call`), `:391` (`_post`, the only socket in the product), `providers/mock.py:141`. Provider contract and `ChatRequest`: `providers/base.py:22, 96`. |
| Where are tools registered? | Two layers. Model-visible schemas: `agent/native.py:49-96` (`_TOOL_SCHEMAS`) plus `tools/terminal.py:terminal_tool_schemas()` appended only when a terminal-capable runtime is passed (`agent/native.py:133-138`). Executable registry: `tools/bounded.py:60-77` (`_OPERATIONS`, `_CAPABILITIES`), dispatch table `tools/bounded.py:315-337`. |
| Where is permission decided? | `permissions/engine.py:552` `authorize()` → `:501` `_evaluate()` (capability, scope, owner, high-risk confirmation) with `:284` `_hard_block_reason()` (unknown action, shell, elevation, process exec, financial, identity, critical) and `:345` `_check_replay()` / `:436` `_authorize_durably()`. Policy table and classifier: `permissions/policy.py:60-145` and `:206` `classify()`. Identity/fingerprints: `permissions/identity.py`. |
| Where does state live? | One SQLite file, owned by `state/durable.py:209` `SQLiteDurableStateStore`. Tables (schema v2): `authorization_replays`, `runtime_tasks`, `action_journal`, `action_events`, `checkpoints`, `reconciliation_events`, `task_verifications`, `task_verification_events`. Open/pragmas: `:251`. File privacy: `state/private_files.py`. |
| Where does recovery enter? | `runtime/durable_runtime.py:154` `recover_task()` (classification only) and `:159` `reconcile()` (trusted observation). Backing store calls: `state/durable.py:864` and `:901`. There is no automatic recovery daemon; a caller invokes it after a restart — see `examples/demos/03_crash_and_reconcile.py`. |
| Who holds completion authority? | `agent/verifier.py:33` `MaintenanceVerifier.verify()`, persisted through `state/durable.py:1016` `record_task_verification()`. The agent loop always calls it and never infers success (`agent/native.py:254`). In Team, the same verifier sits behind a role gate: `team/verifier.py:40` `CompletionAuthority`, `COMPLETING_ROLE = TeamRole.VERIFIER`. |
| Where does Team schedule? | `team/scheduler.py:364` `TeamScheduler.run(task_id, run_id, payload)`, constructed over `team/authority.py:38` `RoleAuthority`. Messages: `team/mailbox.py:158` `Mailbox` with the route table at `:40`. Not reachable from the CLI and not in the wheel. |

## Module map

Read top to bottom; that is also the recommended reading order.

### 1. Contracts — `src/paios_ce/protocols/`

| Path | Key names | Responsibility | Upstream | Downstream |
| --- | --- | --- | --- | --- |
| `protocols/models.py` | `TaskEnvelope:59`, `ActionRequest:105`, `ActionResult:144`, `TaskPlan:160`, `ApprovalRequest:175`, `TaskResult:195`, `AuditEvent:208`, `ErrorEnvelope:126` | All `extra="forbid"` wire models | callers, providers | permissions, state, audit |
| `protocols/enums.py` | `RiskLevel:24`, `Capability:39`, `TaskRiskLevel:15`, `ActionOrigin:55`, `ApprovalState:65` | Shared vocabularies | — | everything |
| `schemas/*.schema.json` | 11 files | The same models as JSON Schema, for external validators | `tools/validate_schemas.py` | CI |

Why first: every other module argues about data shapes defined here.

### 2. Identity and authorization — `src/paios_ce/permissions/`

| Path | Key names | Responsibility |
| --- | --- | --- |
| `permissions/identity.py` | `PrincipalContext`, `AuthorizationIdentity`, `authorization_identity()` | Canonical request + security-context fingerprints; the trusted principal is passed in code, never read from the payload |
| `permissions/policy.py` | `ActionClass`, `ActionRiskPolicy.lookup/classify/security_context` | Static risk table; token-based keyword classification; unknown ⇒ `UNKNOWN_ACTION` |
| `permissions/engine.py` | `PermissionEngine`, `Decision`, `ScopeGuard`, `RiskEngine`, `PermissionResult`, stable `E_*` codes | Deny-by-default decision, hard blocks, scope checks, durable replay |
| `permissions/__init__.py` | re-exports | Public surface |

Upstream: `tools/bounded.py`, `cli/main.py`, `orchestrator`, `speech/service.py`,
`team/adapters/tool_authority.py`. Downstream: `state/durable.py`
(`authorize_replay`), `audit`.

### 3. Durable state — `src/paios_ce/state/`

| Path | Key functions | Responsibility |
| --- | --- | --- |
| `state/durable.py` | `authorize_replay:617`, `prepare_authorized_action:740`, `record_attempt_started:815`, `record_terminal:838`, `mark_uncertain:855`, `recover_task:864`, `reconcile:901`, `journal_entry:936`, `journal_events:945`, `checkpoint:968`, `register_task:995`, `record_task_verification:1016`, `task_verification:1125`, `schema_snapshot:1137` | The single authority for what has been authorized, attempted, settled and verified |
| `state/private_files.py` | `ensure_private_file`, `harden_private_file`, `verify_private_file`, `_NativeWindowsAccessControl` | Owner-only file access on POSIX (mode) and Windows (ACL/SDDL), fail-closed |
| `state/adapter.py` | `StateAdapter`, `NoopStateAdapter`, `SQLiteStateAdapterSkeleton` | Legacy interface stubs kept for compatibility; **not** the durable authority |

Enums worth memorising: `ActionState` (`RECORDED, AUTHORIZED, ATTEMPT_STARTED,
SUCCEEDED, FAILED, UNCERTAIN, RETRY_ELIGIBLE`), `RecoveryClassification`,
`ReconciliationObservation`, `VerificationStatus`.

### 4. Execution ordering — `src/paios_ce/runtime/durable_runtime.py`

`DurableActionRuntime.execute()` (`:71`) is the whole governance story in one
function: require an idempotency key, authorize, persist intent, persist attempt,
call a trusted executor, persist the terminal fact — and on any ambiguity return
`needs_reconciliation=True` instead of guessing. Its constructor refuses an
engine bound to a different store (`:59-61`).

### 5. Tool surface — `src/paios_ce/tools/`

| Path | Key names | Responsibility |
| --- | --- | --- |
| `tools/bounded.py` | `BoundedToolRuntime` (`_OPERATIONS:60`, `execute:128`, `_build_request:170`, `_normalize_parameters:208`, `_relative_path:275`, `_safe_path:290`, `_execute_request:315`, `_run_pytest:420`, `_atomic_write:451`) | The seven named operations, all path/size/bound enforcement, ActionRequest construction |
| `tools/terminal.py` | `TerminalPolicy:65`, `TerminalService:147`, `TerminalToolRuntime:533`, `TerminalEnabledToolRuntime`, `terminal_tool_schemas`, `_SecretRedactor:106`, `MAX_OUTPUT_CHARS:34` | Persistent pty shell sessions, bounded and redacted output, owner-scoped sessions, command policy, shutdown |
| `tools/generate_schemas.py`, `tools/validate_schemas.py` | — | Protocol ⇄ JSON Schema tooling used by CI |

### 6. Proposal sources — `src/paios_ce/providers/`

`base.py` (`Provider`, `ChatRequest`, `ToolCallResult`, `UnsupportedCapability`),
`mock.py` (`MockProvider`, deterministic scripted batches),
`openai_compatible.py` (`OpenAICompatibleProviderConfig:126` with all bounds,
`OpenAICompatibleProvider:156`, `_post:391`), `skeletons.py` (unimplemented
shapes). Every adapter is proposal-only: none imports state or permissions.

### 7. The agent loop and completion — `src/paios_ce/agent/`

| Path | Responsibility |
| --- | --- |
| `agent/native.py` | Bounded proposal loop, batch classification, safe tool-result context, offline provider factory |
| `agent/verifier.py` | The deterministic completion oracle for the maintenance fixture |
| `agent/fixture.py` | `FixtureWorkspace.create/open_existing`, `tree_digest` — fresh trusted copy + baseline digest |
| `agent/repo_task.py` | `RepoTaskRunner`, `RepoTask`, `RepoTaskBudget` — generic governed repository task, no grading |
| `maintenance_artifact.py` (package root) | `MaintenanceCompletionArtifactContract` shared by prompt, tool and verifier |
| `agent/fixtures/aic2026_repo_maintenance/` | The trusted fixture itself (package data) |

### 8. Everything else

| Path | Status | Note |
| --- | --- | --- |
| `cli/main.py` | working | seven subcommands, stable exit codes |
| `config/{loader,models}.py` | working | precedence, `extra="forbid"`, safe defaults |
| `audit/{logger,redact}.py` | working | redaction invariant, `RedactionNotGuaranteedError`, forbidden-key/path rules |
| `health/health.py` | working | local component checks |
| `demo/demo.py` | scaffold-quality | Mock-only closed loop used by `astron demo` |
| `orchestrator/orchestrator.py` | **Scaffold** | composes config/router/provider/engine/worker for a `TaskEnvelope`; it is not the governed task path (demo 1 is) |
| `routing/router.py`, `workers/{base,mock}.py`, `channels/*` | **Scaffold** | interfaces and mocks; no live channel exists |
| `secrets/{base,env,memory}.py` | working | SecretRef indirection; only the `env` backend is exercised |
| `speech/*` | working, optional | Local ASR contracts, policy, faster-whisper adapter, service |

### 9. Team (experimental) — `team/`

| Path | Key names | Responsibility |
| --- | --- | --- |
| `team/scheduler.py` | `TeamScheduler.run:364`, `MAX_*:48-55`, stop reasons, `run_proposals:116` | Drives one bounded role hand-off and the completion call at `:637` |
| `team/authority.py` | `RoleAuthority:38`, `require_tool_authority:106`, `runtime_for:76` | Per-role narrowing of capabilities before the real engine runs |
| `team/adapters/tool_authority.py` | `RoleScopedToolRuntime:133`, `ROLE_TOOL_PROFILES:77-119` | Subclasses `BoundedToolRuntime`; rebuilds its engine/principal per role |
| `team/mailbox.py` | `TeamRole`, `MessageType`, `_ROUTES:40`, `Mailbox:158` | Fixed routes, duplicate-id rejection, monotone `state_version` |
| `team/roles/{base,supervisor,executor,auditor}.py` | `plan/execute/audit` delegates | One-message-in/one-message-out role contracts |
| `team/state.py`, `team/journal.py` | `TeamState`, `TeamActionJournal`, `assert_projection_consistent:161`, `assert_no_unbacked_success:187` | In-memory run facts that must match the durable journal or raise |
| `team/lifecycle.py` | `ActionLifecycle`, `recover:161` | Lifecycle records over `DurableActionRuntime`; recovery is test-reachable only |
| `team/verifier.py` | `CompletionAuthority:40`, `COMPLETING_ROLE:43` | Gate: only the VERIFIER role may request completion |
| `team/mock_provider.py` | `MockLLMProvider:31`, `MaintenanceTeamProvider:79` | Deterministic offline team proposals |
| `team/feedback.py` | `assert_no_hidden_material:37` | **Broken dead code** (undefined `Mapping`, `FORBIDDEN_CONTEXT_KEYS`); kept as committed |

## Reading order for a new contributor

1. `docs/ARCHITECTURE.md` → this file → `agent/native.py` (the loop is 427 lines
   and contains the whole contract).
2. `tools/bounded.py` — read `_normalize_parameters` and `_safe_path` carefully;
   this is where most real-world agent bugs would land.
3. `permissions/engine.py` `_evaluate` + `policy.py` `classify`.
4. `runtime/durable_runtime.py` end to end (196 lines), then
   `state/durable.py` only as far as `prepare_authorized_action`, `recover_task`
   and `reconcile`.
5. `agent/verifier.py` + `maintenance_artifact.py` — the completion rule.
6. `tests/recovery/test_process_crash_recovery.py` and
   `tests/security/test_unknown_action_r1.py` — executable statements of the
   guarantees.
7. `team/scheduler.py` last, with `tests/team/test_scheduler_governed.py` open
   beside it.
