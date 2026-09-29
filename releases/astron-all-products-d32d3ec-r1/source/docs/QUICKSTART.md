# Quick start

Everything here runs offline. No API key, no network call, no model weights.

## 1. Requirements

| Item | Value | Where it comes from |
| --- | --- | --- |
| Python | `>=3.11` | `pyproject.toml` → `requires-python` |
| Build backend | `setuptools.build_meta`, `setuptools>=83,<84` | `pyproject.toml` → `[build-system]` |
| Runtime deps | `pydantic>=2.7,<3`, `PyYAML>=6,<7`, `jsonschema>=4.20,<5`, `pytest>=9.0.3,<10` | `[project.dependencies]` |
| Extras | `dev` (coverage, pytest-cov), `speech` (faster-whisper) | `[project.optional-dependencies]` |
| Import package | `paios_ce` (historical name, kept for compatibility) | `src/paios_ce/` |
| Distribution name | `astron`, version `0.1.0rc2` | `[project]` |
| Console scripts | `astron` (primary), `paios-ce` (legacy alias) → `paios_ce.cli.main:main` | `[project.scripts]` |

`pytest` is a **runtime** dependency on purpose: the bounded test tool executes
`python -m pytest tests -q` as a fixed, non-model-controlled subprocess
(`src/paios_ce/tools/bounded.py:420-448`).

## 2. Install

```bash
cd project                       # the directory holding pyproject.toml
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Then the four commands that prove the install is real:

```bash
astron health
astron demo
astron validate-config
astron run-task examples/unknown_action_fixture.json; echo "exit=$?"
```

Expected:

* `health` — a JSON list of component checks, all local, no secret or path leaks.
* `demo` — `"task_result_status": "success"`, one `"allow"` decision, and
  `"audit_event_count": 3`. This is the Mock Provider exercising the contract
  chain, not a model.
* `validate-config` — `"valid": true` plus the effective configuration with the
  owner allowlist excluded. Works with no config file at all; the built-in
  defaults are the safe ones (`127.0.0.1`, `public_bind=false`, `dm_only=true`,
  speech disabled, redaction on).
* the unknown-action fixture — `"decision": "blocked"`,
  `"action_class": "UNKNOWN_ACTION"`, `"error_code": "E_UNKNOWN_ACTION"`,
  `"execution_attempted": false`, and **exit code 5**.

Stable CLI exit codes: `0` ok, `2` usage, `3` configuration/validation,
`4` denied, `5` blocked, `6` internal
(`src/paios_ce/cli/main.py:3-9`).

## 3. The three offline demos

```bash
bash examples/demos/01_governed_task.sh        # governed task → verified completion
bash examples/demos/02_permission_denial.sh    # allow, deny, hard block, scope escape
python examples/demos/03_crash_and_reconcile.py # real mid-action crash → reconcile
```

Each prints its own temporary artifact directory and writes nothing into the
repository. See [examples/demos/README.md](../examples/demos/README.md) for the
expected output of each step.

## 4. Run the tests

From the repository root (this matters — `team/` sits outside the installed
package, and `tests/conftest.py` assumes the repo layout):

```bash
python -m pytest -ra -q
```

Result on this delivery copy: `546 passed, 1 skipped` (the skip is a
filesystem-junction case). Targeted suites:

```bash
python -m pytest tests/recovery -ra -q     # real cross-process crash windows
python -m pytest tests/security -ra -q     # hard blocks, unknown action, redaction
python -m pytest tests/state tests/runtime tests/regression -ra -q
python -m pytest tests/phase3 tests/agent tests/terminal -ra -q
python -m pytest tests/team -ra -q         # experimental Team path
```

## 5. Optional: a real model

A live provider is never implied. You must pass all three of `--base-url`,
`--model` and `--api-key-env`, and the last one is the **name** of an environment
variable, not a key:

```bash
export MY_PROVIDER_KEY=...
astron maintenance-demo --mode live \
  --base-url https://api.example.com/v1 \
  --model <provider-model-id> \
  --api-key-env MY_PROVIDER_KEY \
  --workspace "$(mktemp -d)/ws" --state-db "$(mktemp -d)/state.sqlite"
```

Behaviour worth knowing before you try it:

* Missing any of the three → `{"status": "BLOCKED_EXTERNAL_CREDENTIAL"}`, exit 3.
  No fallback to Mock.
* `--provider-timeout` is bounded to 1-120 s, `--max-output-tokens` to 1-4096
  (`providers/openai_compatible.py:147-150`).
* The provider is a proposal source only. It cannot execute a tool, choose a
  principal, or write a completion.
* Model-visible surface is fixed: at most one mutating action per turn, or a
  batch of two to four calls that are all read-only
  (`agent/native.py:23-24, 193-209`).

## 6. Optional: local speech

```bash
pip install -e ".[speech]"
# then a private config with speech.enabled: true
astron transcribe sample.wav --model tiny --language en --device cpu --compute-type int8
```

Disabled by default, `local_files_only` by default, owner-only permission, and
audit events carry metadata rather than transcript text. Full contract:
[LOCAL_ASR.md](LOCAL_ASR.md).

## 7. Platform notes

| Platform | Core, CLI, demos | `terminal_*` | Private-state hardening |
| --- | --- | --- | --- |
| macOS | works; upstream validation base and this copy's re-check | works (POSIX pty, `/bin/zsh` else `/bin/sh`) | POSIX mode `0700/0600`, verified fail-closed |
| Linux | expected to work; not re-validated in this delivery | expected (pty) — the backend is described as macOS-first | POSIX mode |
| Windows | no OS-specific code in the core path; not re-validated here | **not implemented** (`tools/terminal.py` needs `os.openpty`) | real ACL/SDDL backend in `state/private_files.py` |

Upstream `SUPPORT_MATRIX.md` records `CURRENT_COMPETITION_REVISION_WINDOWS_RUNTIME=NOT_RUN`
and `..._UBUNTU_RUNTIME=NOT_RUN`. Do not upgrade those to "supported" on the
strength of this table — it describes what the code can do, not what has been
certified.
