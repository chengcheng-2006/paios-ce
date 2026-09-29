# Developer guide

Interface stability: everything below is an **experimental** surface. The
`SUPPORT_MATRIX.md` labels each module `EXPERIMENTAL` or `Scaffold`; there is no
guarantee of a stable SDK across releases, and this guide does not invent one.
Where a snippet is not a real importable path it is marked.

All snippets assume `pip install -e ".[dev]"` from the repository root and
`PYTHONPATH=src:.` when touching `team/`.

## 1. Run one governed task programmatically

This mirrors `cli/main.py:95-118`, which is the production wiring:

```python
from pathlib import Path

from paios_ce.agent import MaintenanceVerifier, NativeAgent, offline_maintenance_provider
from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.state import SQLiteDurableStateStore
from paios_ce.tools import BoundedToolRuntime

workspace = FixtureWorkspace.create(Path("/tmp/ws/fixture"))       # fresh trusted copy
with SQLiteDurableStateStore(Path("/tmp/ws/state.sqlite")) as store:
    tools = BoundedToolRuntime(workspace.root, store)
    result = NativeAgent(
        offline_maintenance_provider("my-task"),                   # or a real Provider
        tools,
        MaintenanceVerifier(tools, workspace.baseline_digest),
        model_id="mock-1",
    ).run("my-task")

print(result.accepted, result.verifier.reason_code, [a["operation"] for a in result.actions])
```

`NativeTaskResult` fields: `task_id`, `accepted`, `verifier`, `actions`,
`provider_error`, `provider_diagnostics`, `request_contract_snapshot`,
`response_tool_call_metadata`, `exhausted`. Bounds: `max_steps` 1-12 (default 6),
`task_timeout_seconds` 1-300 (default 60).

`BoundedToolRuntime` also offers `execute_direct(...)`, which runs the same
normalized operation **without** governance. It requires a runtime built with
`state_store=None` (`tools/bounded.py:149-168`) and exists for measurement
comparisons — never use it in an application path.

## 2. Add a provider (proposal source)

Subclass `paios_ce.providers.base.Provider` (`providers/base.py:96`). The loop
only calls `tool_call(ChatRequest) -> ToolCallResult`.

```python
from paios_ce.providers import ChatRequest, Provider, ProviderHealth, ToolCallResult

class MyProvider(Provider):
    def get_capabilities(self):                       # -> list of Capability
        return []                                     # advertise honestly
    def tool_call(self, request: ChatRequest) -> ToolCallResult:
        # request.messages, request.tools (JSON-schema dicts), request.max_tokens
        return ToolCallResult(
            tool_calls=[{"id": "call-1", "type": "function",
                         "function": {"name": "workspace.read_text",
                                      "arguments": '{"path": "README.md"}'}}],
            model_id=request.model_id,
            trace_id=request.trace_id,
        )
    def health_check(self) -> ProviderHealth:
        return ProviderHealth(status="ok", provider_id="mine")
```

Contract notes that will bite you otherwise:

* `function.arguments` must be a **JSON string** of an object, ≤ 16 384 bytes
  (`agent/native.py:268-282`);
* every call needs a non-empty, unique `id` ≤ 128 bytes, or the turn is rejected
  as `INVALID_MODEL_OUTPUT` (`agent/native.py:284-293, 202-204`);
* only `workspace.list_files` and `workspace.read_text` may appear more than once
  in one turn (`READ_ONLY_BATCH_ALLOWLIST`);
* raising is safe: the loop records `provider_error` from `exc.code` or the class
  name, truncated to 96 chars, and reads an optional `safe_diagnostics` dict
  (`agent/native.py:180-184, 391-394`). Never put a secret in an exception.

The reference implementation to copy from is `providers/openai_compatible.py`
(its `_post` at `:391` is the only network call in the product).

## 3. Add a tool — five places, on purpose

A tool is not "just a function". Registering one changes the model-visible
surface, the trusted normalization, and the risk policy, and Astron requires all
three to be written deliberately.

| # | File | What you add |
| --- | --- | --- |
| 1 | `agent/native.py:49-96` `_TOOL_SCHEMAS` | the function schema the model sees |
| 2 | `tools/bounded.py:60-77` `_OPERATIONS`, `_CAPABILITIES` | the allowlisted name and the capability it needs |
| 3 | `tools/bounded.py:215-223` `allowed` map in `_normalize_parameters` | the exact parameter names accepted, plus validation and bounds |
| 4 | `tools/bounded.py:315-337` `_execute_request` handler map + a private `_your_op` method | the effect, with size/time/output bounds and an `ActionResult` |
| 5 | `permissions/policy.py:226-240` operation map (and, if new, an `ActionClass` + `PolicyDecision` row at `:71-140`) | how it is classified and at what risk |

Then grant the capability where the engine is constructed
(`tools/bounded.py:104-113`) and, for Team, in the relevant role profile
(`team/adapters/tool_authority.py:77-119`).

Two rules that must survive your change:

* never take a path, URL, command or executable from model parameters as a
  root/argument — reuse `_relative_path` / `_safe_path`
  (`tools/bounded.py:274-313`) and keep `network_scope={"mode": "none"}` unless
  you have genuinely added an egress class to the `ScopeGuard`;
* an operation that maps to no `ActionClass` becomes `UNKNOWN_ACTION` and is hard
  blocked — that is the safety net, not a bug to route around.

For a larger, less invasive option, look at `tools/terminal.py`: it adds six
operations as a separate runtime (`TerminalToolRuntime`) that is *composed* with
the bounded one via `TerminalEnabledToolRuntime` and only widens the agent loop
when explicitly passed (`agent/native.py:133-138`). Follow that pattern — a
capability that can be switched off is easier to reason about than one baked into
the base registry.

## 4. Define a task

Three real shapes:

**a. `TaskEnvelope` JSON** (`protocols/models.py:59`), consumed by
`astron run-task examples/demo_task.json`. Required: `task_id`, `request_id`,
`origin`, `owner_identity`, `intent` (≤ 128 chars), plus `requested_capabilities`,
`constraints`, `attachments`, `risk_level`, `approval_state`, `trace_id`.
`extra="forbid"` — a stray key is a validation error, exit 3.
This path runs through `MinimalOrchestrator`, which is labelled **Scaffold**.

**b. `ActionRequest` JSON** — if the file has `action_id` and `operation`,
`run-task` sends it straight through the `PermissionEngine`
(`cli/main.py:309-313`). This is the "will the runtime accept this proposal"
fixture used by demo 2. The trusted principal comes from `--principal-id` or the
CLI default, never from the JSON.

**c. `RepoTask`** for a real repository task (`agent/repo_task.py:56`):

```python
from pathlib import Path
from paios_ce.agent import RepoTask, RepoTaskBudget, RepoTaskRunner
from paios_ce.providers import MockProvider

task = RepoTask(
    task_id="fix-timeout",
    workspace_root=Path("/tmp/prepared/checkout"),      # must be a clean git checkout
    problem_statement="DEFAULT_TIMEOUT_SECONDS breaks the interactive path.",
    budget=RepoTaskBudget(max_model_turns=12, max_wall_clock_seconds=300,
                          max_model_calls=12, max_output_tokens=1024),
    allowed_tools=("workspace.list_files", "workspace.read_text",
                   "workspace.patch_text", "test.run_pytest_bounded"),
    base_commit="<expected sha>",                        # optional pin
)
result = RepoTaskRunner(MockProvider(), model_id="mock-1",
                        runtime_root=Path("/tmp/astron-runtime")).run(task)
print(result.status_after, result.runtime_status, result.files_changed)
```

The runner rejects a dirty checkout before the first provider call, forbids
evaluator-only metadata keys (`fail_to_pass`, `gold_patch`, `test_patch`, …), and
returns `AGENT_STOPPED` / `BUDGET_EXHAUSTED` — never a solved verdict.

## 5. Add a verifier (completion authority)

Anything with `verify(task_id, *, step=...)` returning an object exposing
`.accepted` and `.reason_code` can be injected:

```python
from paios_ce.state import VerificationStatus

class DiffShrinkVerifier:
    """Accept only when the bounded suite passes and the diff stays small."""

    VERSION = "diff-shrink-v1"

    def __init__(self, tools, store):
        self._tools, self._store = tools, store

    def verify(self, task_id, *, step: int = 90):
        run = self._tools.execute(task_id, step, "test.run_pytest_bounded", {})
        ok = (run.executor_invoked and not run.needs_reconciliation
              and run.result is not None
              and run.result.outcome.get("status") == "PASSED")
        return self._store.record_task_verification(
            task_id,
            VerificationStatus.ACCEPTED if ok else VerificationStatus.REJECTED,
            "DIFF_SHRINK_ACCEPTED" if ok else "DIFF_SHRINK_TESTS_FAILED",
            self.VERSION,
            {"task_id": task_id},
        )
```

Rules the packaged verifier shows you:

* persist through `SQLiteDurableStateStore.record_task_verification` so the
  decision is a durable fact with a version string and evidence, not a return
  value (`state/durable.py:1016`);
* verify **state**, not claims — `agent/verifier.py:95-129` rejects any file
  change outside the one permitted source file and re-parses the artifact against
  the shared contract;
* keep verification independent of the model. If your verifier asks the model
  whether it finished, you no longer have a completion authority;
* run tests through the bounded tool so verification is itself governed and
  journaled.

`MaintenanceVerifier` is a **fixed oracle for one fixture**, not a general
repository verifier. Building a general one is the single largest honest gap in
the product today.

## 6. Handle uncertainty in your own executor

If your executor has an external side effect, write it so a
`Reconciler` can answer "did it happen?" from evidence:

```python
from paios_ce.state import ReconciliationObservation
from paios_ce.runtime import DurableActionRuntime

class InvoiceReconciler:
    def __init__(self, api):
        self._api = api

    def observe(self, journal):                     # no execution here
        if self._api.exists(journal.idempotency_key):
            return ReconciliationObservation.CONFIRMED_SUCCEEDED
        return ReconciliationObservation.NO_EVIDENCE   # stays UNCERTAIN

recovery = runtime.recover_task(task_id)
if recovery.classification.value == "NEEDS_RECONCILIATION":
    result = runtime.reconcile(recovery.journal.journal_id, InvoiceReconciler(api))
```

`CONFIRMED_NOT_APPLIED` moves the journal to `RETRY_ELIGIBLE` — still without
executing. `NO_EVIDENCE` appends an event and leaves the action uncertain. That
asymmetry is the point: Astron would rather stall than duplicate a side effect.

## 7. Use the Team layer (experimental)

```python
from paios_ce.agent.fixture import FixtureWorkspace
from paios_ce.state import SQLiteDurableStateStore
from team.authority import RoleAuthority
from team.mock_provider import MaintenanceTeamProvider
from team.scheduler import TeamScheduler

workspace = FixtureWorkspace.create(Path("/tmp/team/fixture"))
with SQLiteDurableStateStore(Path("/tmp/team/state.sqlite")) as store:
    authority = RoleAuthority(workspace.root, store)
    result = TeamScheduler(authority, workspace.baseline_digest,
                           MaintenanceTeamProvider()).run(
        "team-task", "team-run", {"objective": "repair the fixture timeout"})

print(result.status, result.task_completed, dict(result.verification))
print(len(result.messages), len(result.actions), len(result.refused_actions))
```

What Team adds for you: a role profile gate before the engine
(`RoleAuthority.require_tool_authority`, `team/authority.py:106`), so a Supervisor
with `capabilities=frozenset()` cannot even reach authorization; a mailbox that
refuses unroutable or duplicated messages; a journal projection that raises if a
run claims a success with no durable row
(`team/journal.py:assert_no_unbacked_success`); and a completion gate that throws
`CompletionAuthorityViolation` unless the request comes from `VERIFIER`
(`team/verifier.py:80-85`).

What you must decide before using it: `max_executor_rounds` (default 1), and a
`verifier` that fits your task, since the packaged default only understands the
maintenance fixture.

## 8. Testing your change

```bash
python -m pytest -ra -q                        # whole suite, must stay green
python -m pytest tests/security -ra -q          # hard blocks, unknown action, redaction
python -m pytest tests/recovery -ra -q          # real crash windows
python -m paios_ce.tools.validate_schemas --schemas schemas   # repo root only
python tools/validate_security_workflow.py
python tools/security_local_scan.py .
python tools/package_local_validate.py --outdir "$(mktemp -d)"
```

When you add a tool, the minimum honest test set is: happy path; parameter that
is not in the allowlist; path traversal and symlink escape; size bound;
denied-capability case; and an assertion that a rejected action recorded
`execution_attempted=false`. `tests/phase3/test_bounded_tools_and_e2e.py` and
`tests/security/test_unknown_action_r1.py` are the templates to copy.

Do not relax an existing assertion to make a change pass. Several tests in this
repository exist specifically to fail if someone weakens a guarantee, and
`tools/validate_security_workflow.py` checks that the security invariants of the
CI workflow still hold.
