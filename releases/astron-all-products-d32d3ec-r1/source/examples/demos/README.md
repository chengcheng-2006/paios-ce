# Offline demos

Three representative runs plus one experimental appendix. All of them are
deterministic, need no API key, make no network request, and write only inside a
fresh temporary directory. They are **not** simulations either: the permission
engine, the durable SQLite journal, the bounded tools and the verifier that run
here are the same objects the library uses.

The one thing to keep in mind: the bounded test tool starts a real `pytest`
subprocess, and the fixture repair writes real files. So these runs are
model-free and network-free, but not process-free. Run them from the repository
root after `pip install -e ".[dev]"`.

| # | Command | Shows | Does not show |
| --- | --- | --- | --- |
| 1 | `bash examples/demos/01_governed_task.sh` | one task proposed by an offline provider, executed under governance, accepted by the verifier | a real model's judgement |
| 2 | `bash examples/demos/02_permission_denial.sh` | deny, hard-block and scope-escape decisions, with `execution_attempted=false` | OS-level containment of a process that was never started |
| 3 | `python examples/demos/03_crash_and_reconcile.py` | a real child process killed mid-action, then reconstructed from the journal and reconciled | exactly-once delivery against an arbitrary external system |
| 4 (experimental) | `PYTHONPATH=src:. python examples/demos/04_team_offline_run.py` | the Team role loop wired to the same engine, store and verifier | a CLI or installed-package entry point — Team has neither |

## Where the artifacts go

Each script prints its own `mktemp -d` path at the first line, e.g.
`/var/folders/.../astron-demo1-XXXXXX` on macOS, `/tmp/astron-demo1-XXXXXX` on
Linux. Nothing is written into the repository.

* `state.sqlite` — durable authorization, journal, events, checkpoint and
  verification facts.
* `baseline/`, `workspace/` — fresh copies of the trusted maintenance fixture.
* `workspace/.astron-artifacts/change_summary.json` — the completion artifact the
  verifier requires.
* `ledger.txt` (demo 3) — the stand-in external side effect the reconciler reads.

Temporary directories are left in place so you can inspect them; delete them when
done. Demo 1 additionally prints the three `sqlite3` queries that read the
durable facts back.

## Expected shape of the output

* Demo 1: `maintenance-baseline` reports
  `"baseline_status": "FAIL_AS_EXPECTED"`, then `maintenance-demo` reports
  `"status": "PASS"` with `"verifier": "VERIFIER_ACCEPTED"` and seven governed
  actions: three read-only `workspace.read_text` calls in one batch, then
  `workspace.patch_text → test.run_pytest_bounded → workspace.write_artifact →
  validate.json`.
* Demo 2: one `allow` (exit 0), then `blocked` with
  `E_UNKNOWN_ACTION`-style reasons and exit 5 for the hard blocks, `deny` and
  exit 4 for the capability/scope rejections. Every rejection reports
  `"execution_attempted": false`.
* Demo 3: child exit code 72, `NEEDS_RECONCILIATION`, an event trail of
  `RECORDED → AUTHORIZED → ATTEMPT_STARTED → UNCERTAIN → SUCCEEDED`, and a
  ledger that still contains exactly one line.
* Demo 4: `status: VERIFIED_SUCCESS`, five routed messages
  `HARNESS → SUPERVISOR → EXECUTOR → AUDITOR → VERIFIER → HARNESS`.

## Reading the same guarantees as tests

```bash
python -m pytest tests/recovery -ra -q          # real cross-process crash windows
python -m pytest tests/security -ra -q          # unknown action, hard blocks, redaction
python -m pytest tests/phase3 -ra -q            # bounded tools, agent loop, artifact contract
python -m pytest tests/state tests/runtime -ra -q
python -m pytest tests/team -ra -q              # experimental Team path
```
