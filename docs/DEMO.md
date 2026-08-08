# Demo Guide

The bundled demo is intentionally local and deterministic. It exists to
exercise the public contracts without a real model provider, API key, live
channel, or system capability.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Health check

```bash
paios-ce health
```

Expected properties:

- components report safe local status;
- no secret value is printed;
- no full environment dump is printed;
- no private configuration value is printed.

## Local demo

```bash
paios-ce demo
```

The command exercises:

```text
local input
→ TaskEnvelope
→ runtime configuration
→ minimal router
→ Mock Provider
→ TaskResult
→ redacted audit events
```

The exact JSON formatting may evolve, but the command must remain deterministic
for a fixed fixture and must not require network access or credentials.

## Configuration validation

```bash
paios-ce validate-config
```

The command validates configuration precedence and emits a redacted view of the
effective configuration.

## Task fixture

```bash
paios-ce run-task examples/demo_task.json
```

The fixture must contain placeholders only.

## Fail-closed checks

Use the repository's negative fixtures and tests to verify that:

- unknown actions do not execute;
- critical actions are hard-blocked;
- arbitrary shell is hard-blocked;
- administrator elevation is hard-blocked;
- missing capabilities deny execution;
- out-of-scope filesystem or network targets deny execution;
- replayed actions are detected according to policy.

## Local ASR preview

Install the optional speech dependency:

```bash
pip install -e ".[dev,speech]"
```

Enable the capability in a private configuration (`speech.enabled: true`) and
transcribe a local file with a cached model:

```bash
paios-ce transcribe sample.wav \
  --model tiny \
  --language en \
  --device cpu \
  --compute-type int8
```

Speech is disabled by default and defaults to `local_files_only`. The
transcript is returned to the caller only; audit events carry metadata
(counts, language, model label), never transcript text. See
[`docs/LOCAL_ASR.md`](LOCAL_ASR.md).

## Test suite

```bash
python -m pytest -ra -q
```

Coverage-equivalent command:

```bash
python -m pytest \
  --cov=paios_ce \
  --cov-branch \
  --cov-report=term-missing \
  -ra -q
```

## Safe recording rules

When capturing demo output for documentation:

- use a fresh public clone;
- use no real environment secrets;
- avoid usernames and absolute local paths;
- inspect all output before publishing;
- do not publish `.env`, browser profiles, shell history, or private config;
- label Mock behavior as Mock behavior.

A future GIF or video should be generated from this real CLI flow rather than
from a fictional interface.
