# Demo script (4 minutes, CLI only)

> 版本与证据边界：本文介绍产品快照 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`；如提及 R2 评测数字，其测量运行来自 `13ee283ce8b6121af14b1bf0f1f9deefe1484cf2`。d32d3ec 本身没有正式模型实跑证据。


No slides are needed for the middle of this. Everything is the real CLI and real
files on disk. No API key and no network are needed. The product is demonstrated
through its CLI; the separate static evidence viewer is not part of this walkthrough.

**Setup before you start talking** (~2 minutes, done in advance):

```bash
cd project
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -ra -q          # 546 passed, 1 skipped — keep the tail on screen
```

Terminal size: 100+ columns. Have `sqlite3` installed for step 3.

---

### 0:00 – 0:35 — The problem, with a live example

> "If tool permissions exist only in a model prompt, the prompt itself cannot
> serve as a trusted authorization check. Astron evaluates an untrusted proposal
> through its own permission engine before any action is attempted."

```bash
astron run-task examples/unknown_action_fixture.json; echo "exit=$?"
```

> "This is Astron. Same JSON shape, same untrusted proposal — and a real
> permission engine answers."

Point at three fields in the output:

```text
"action_class": "UNKNOWN_ACTION"
"error_code":  "E_UNKNOWN_ACTION"
"execution_attempted": false
```

> "`execution_attempted: false` is the whole project in two words. The model
> proposed; the runtime decided; nothing happened. Exit code 5."

---

### 0:35 – 1:45 — A real governed task, end to end

```bash
bash examples/demos/01_governed_task.sh
```

Narrate the two phases as they scroll:

1. **`maintenance-baseline`** — `FAIL_AS_EXPECTED`. We certified that the trusted
   fixture genuinely fails *before* any model is involved. Otherwise a later
   "success" means nothing.
2. **`maintenance-demo --mode mock`** — the proposals here are deterministic Mock
   output, and that is the point: it proves the harness, not a model's cleverness.

Then read the result fields:

```text
"status":   "PASS"
"verifier": "VERIFIER_ACCEPTED"
"actions":  ["workspace.read_text", … , "test.run_pytest_bounded",
             "workspace.write_artifact", "validate.json"]
```

> "Three read-only calls were allowed to batch. Every mutating step was alone in
> its turn, because the runtime rejects mixed batches before the first call. The
> file really changed, the bounded pytest really ran, the completion artifact
> really validated against a trusted schema."

```bash
open "$TMPDIR"/astron-demo1-*/workspace   # or: cat the two paths the demo printed
```

Show `maintenance_config.py` and `.astron-artifacts/change_summary.json`.

> "And notice what did **not** happen: nobody asked the model whether it was
> finished. A deterministic verifier checked the filesystem, the forbidden
> mutations, the tests and the artifact — and it is the only thing that can move
> a task to complete."

---

### 1:45 – 2:50 — The part that makes this a runtime, not a wrapper

```bash
bash examples/demos/02_permission_denial.sh
```

One screen, five outcomes: an in-scope read `allow`; two unregistered action names
`blocked` as `UNKNOWN_ACTION` - and the second one also requests cloud egress, so
you can say that an unknown name is rejected on the name, *before* scope is even
consulted; shell syntax `blocked` as `PROCESS_EXEC`; an out-of-class read `deny`.
Every rejection carries `execution_attempted: false`.

Then the crash:

```bash
python examples/demos/03_crash_and_reconcile.py
```

> "That child process really died — `os._exit` after its side effect, before the
> terminal outcome. Any system that performs side effects needs to handle this
> failure window explicitly."

Read the four lines that matter:

```text
child exit code: 72
recover_task -> classification=NEEDS_RECONCILIATION, journal state=UNCERTAIN
executor_invoked=False  needs_reconciliation=True  ledger still has 1 side effect(s)
observation=CONFIRMED_SUCCEEDED new state=SUCCEEDED
```

> "An identical proposal is refused — no blind retry. A *different* principal
> reusing the same idempotency key is blocked with
> `E_IDEMPOTENCY_KEY_REUSE_MISMATCH`. Only a trusted observer reading the ledger
> can settle the action, and even then the executor never runs again.
> Rebuild state, re-execute an action, confirm an external effect — three
> different operations, and calling all three 'replay' is how duplicates ship."

The receipt, live:

```bash
sqlite3 <state.sqlite printed by step 1> \
  'select sequence,state,event_kind from action_events order by sequence'
```

```text
1 RECORDED        JOURNAL_RECORDED
2 AUTHORIZED      AUTHORIZATION_RECORDED
3 ATTEMPT_STARTED ATTEMPT_STARTED
4 UNCERTAIN       RECOVERY_CLASSIFIED_UNCERTAIN
5 SUCCEEDED       RECONCILED_SUCCESS
```

---

### 2:50 – 3:30 — Where the code is, and how you extend it

```bash
sed -n '71,100p' src/paios_ce/runtime/durable_runtime.py
```

> "This one function is the governance story: authorize, persist intent, persist
> attempt, invoke a trusted executor, persist the terminal fact, and on any
> ambiguity return `needs_reconciliation` instead of guessing."

Orientation for reviewers, in order:

```text
docs/SOURCE_MAP.md      answers: where is the entry point, the model call, the
                        tool registry, the permission decision, the state, the
                        recovery door, and who holds completion authority
docs/ARCHITECTURE.md    call chain + the action lifecycle state machine
docs/DEVELOPER_GUIDE.md adding a tool is a five-place change, on purpose
```

Optional, only if asked: Team mode —
`PYTHONPATH=src:. python examples/demos/04_team_offline_run.py` prints
`HARNESS → SUPERVISOR → EXECUTOR → AUDITOR → VERIFIER → HARNESS` with
`VERIFIED_SUCCESS`. Say the status out loud: experimental, one bounded round by
default, no CLI entry, not in the wheel.

---

### 3:30 – 4:00 — Boundaries, said before anyone asks

> "Three limits, deliberately. The packaged verifier is a fixed oracle for one
> fixture — a general repository verifier is the biggest honest gap. Bounded test
> execution is a real pytest subprocess; 'restricted' is not 'read-only' and not
> an OS sandbox. And the measurement story: R2 ran 120 formal runs across
> Direct, Single and Team, and the capability subset came out as a floor effect —
> zero of seventy-two in all three arms, with twenty-three provider errors
> censoring the arms differently. R2 established no advantage for Astron. R3 is
> still calibrating on a development set. What I am demonstrating today is the
> mechanism and its failure semantics, all of it offline and repeatable."

Close on the first command again:

```bash
astron run-task examples/unknown_action_fixture.json; echo "exit=$?"
```

> "The model proposes. The runtime decides. The verifier completes."

---

## If something goes wrong on stage

| Symptom | Cause | Fix |
| --- | --- | --- |
| `astron: command not found` | venv not activated | `source .venv/bin/activate` |
| demo 1 ends `REJECTED` with `VERIFIER_TEST_FAILED` | a stray `.pyc`/cache in a reused workspace | demos always create a fresh `mktemp -d`; re-run |
| demo 3 says `child stderr: …` | `src/` not importable from the child | run from the repository root, or `pip install -e ".[dev]"` |
| `sqlite3: command not found` | not installed | read the same facts with `python -c "from paios_ce.state import SQLiteDurableStateStore as S; print(S('…').journal_events('…'))"` |
| `ModuleNotFoundError: team` | Team is not in the wheel | prefix with `PYTHONPATH=src:.` |
| pydantic `Field name "schema" …` warnings | known upstream naming warning, stderr only | harmless; demos set `PYTHONWARNINGS` |

Never record a take that falls back to a canned screenshot. If a step fails, say
so, fix it live, and re-run — the demos take seconds.
