# Configuration

Two YAML layers plus environment plus CLI flags, merged by
`src/paios_ce/config/loader.py`. Every model uses `extra="forbid"`, so an unknown
key is a hard error rather than a silently ignored typo.

## Precedence (highest wins)

```text
1. CLI flags            (explicit overrides dict passed to ConfigLoader.load)
2. process environment  (PAIOS_CE_* variables)
3. private local config (--private-config FILE)
4. public project config(--public-config FILE)
5. built-in safe defaults (the RuntimeConfig field defaults)
```

There are **no implicit config paths**. If you do not pass `--public-config` or
`--private-config`, layer 5 alone applies — which is deliberately the safe
configuration. `astron validate-config` with no arguments is therefore a
meaningful command: it prints what a fresh, unconfigured runtime will do.

## Inspecting the effective configuration

```bash
astron validate-config \
  --public-config examples/public_config.example.yaml \
  --private-config examples/private_config.example.yaml
```

Returns `"valid": true` plus the merged view. Two facts about that view:

* `owner_allowlist` is excluded from the emitted `effective` object
  (`cli/main.py:216`);
* a bad file raises `ConfigLoadError` → `"valid": false` and exit code 3.

## Public config (`PublicConfig`)

Project-level, committable, non-secret. Template:
`examples/public_config.example.yaml`.

| Block | Fields | Safe default |
| --- | --- | --- |
| top | `schema`, `profile` (`minimal`), `runtime_profile` (`lite`) | schema literal pinned to the v0.1 URL |
| `defaults` | `listen`, `public_bind`, `public_bind_risk_acknowledged`, `dm_only`, `group_execution`, `group_execution_risk_acknowledged`, `owner_allowlist_required`, `high_risk_confirmation`, `raw_audio_storage`, `temp_audio_delete`, `cloud_asr`, `remote_execution` | `127.0.0.1`, no public bind, DM-only, no group execution, no raw audio, `cloud_asr: opt_in_only`, no remote execution |
| `capabilities` | `providers[]`, `channels[]`, `speech[]`, each with `support_level` and an optional `credential_ref` | empty lists |
| `audit` | `redact_secret_values`, `redact_paths`, `redact_endpoints`, `transcript_retention_days` | all redaction `true`, retention `0` |
| `installer` | `selected_profile`, `optional_components_eligible` | no optional components |

## Private config (`PrivateConfig`)

Machine-local, never committed. Template:
`examples/private_config.example.yaml`.

| Block | Notes |
| --- | --- |
| `owner_allowlist` | list of trusted principals, e.g. `principal:example.invalid/owner-1` |
| `providers.primary` / `.fallback` | `id`, `endpoint`, `credential_ref` — an endpoint is a URL, a credential ref is a **name** |
| `channels.local_web` | `listen`, `port`, `public_bind`, `public_bind_risk_acknowledged` |
| `channels.cli` | `enabled` |
| `speech` | `enabled: false` by default; `local_files_only`, `max_file_size_mb`, `max_duration_seconds`, `allowed_extensions`, `vad_filter`, `device`, `compute_type`, `default_model`, `raw_audio_storage`, `transcript_retention_days` |
| `state` | `sqlite_path`, `model_cache_path` (the templates use a `<USER_HOME>` placeholder — expand it yourself; nothing is created for you) |
| `group_execution` | `enabled: false`, `risk_acknowledged: false` |

## Secrets

`SecretRefDecl` declares `backend` as one of
`env | oskeyring | dpapi | file | external_manager | prompt_once` with a `ref`
map. Only `env` is exercised by the CLI paths in this snapshot
(`secrets/env.py`, plus `secrets/memory.py`).

Rules that hold in code, not just in prose:

* the provider config takes `api_key_env`, validated as an environment-variable
  *name* (`[A-Z][A-Z0-9_]{0,127}`), and reads `os.environ` lazily at request time
  (`providers/openai_compatible.py:143, 168`);
* `base_url` must be an absolute http(s) URL with no credentials, query or
  fragment;
* config templates contain placeholders only
  (`example.invalid`, `127.0.0.1`, `not-a-valid-provider-token`);
* the audit layer redacts secret-shaped keys and values and refuses to emit an
  event it cannot prove is redacted (`audit/redact.py`).

## Environment variables

Only a fixed allowlist is translated; unknown `PAIOS_CE_*` names are ignored so
the surface stays explicit (`config/loader.py:57-116`):

```text
PAIOS_CE_DEFAULTS_LISTEN                 PAIOS_CE_DEFAULTS_CLOUD_ASR
PAIOS_CE_DEFAULTS_PUBLIC_BIND            PAIOS_CE_PROFILE
PAIOS_CE_DEFAULTS_GROUP_EXECUTION        PAIOS_CE_RUNTIME_PROFILE
PAIOS_CE_DEFAULTS_REMOTE_EXECUTION       PAIOS_CE_PRIMARY_PROVIDER
PAIOS_CE_DEFAULTS_RAW_AUDIO_STORAGE      PAIOS_CE_PROVIDER_ENDPOINT
PAIOS_CE_DEFAULTS_DM_ONLY                PAIOS_CE_PROVIDER_CREDENTIAL_REF_BACKEND
PAIOS_CE_OWNER_ALLOWLIST (comma list)    PAIOS_CE_PROVIDER_CREDENTIAL_REF_ENV_VAR
```

Boolean variables are read case-insensitively for the *value*
(`1|true|yes|on` are true, anything else false) but the `PAIOS_CE_*` **names**
are matched case-sensitively against the process environment.

## Durable-state configuration

`SQLiteDurableStateStore` has no YAML knob — it is constructed with a path (the
CLI flags `--state-db`) and enforces its own durability contract
(`state/durable.py:251-290`):

* refuses to open unless `PRAGMA foreign_keys=ON`, `journal_mode=WAL` and
  `synchronous=FULL` are all actually granted — otherwise
  `StateStoreUnavailable`;
* `busy_timeout` default 1000 ms, written transactions use `BEGIN IMMEDIATE`;
* the database file is created `0o600` and re-verified on every open, including
  the `-wal`/`-shm` sidecars; POSIX mode on macOS/Linux, an ACL/SDDL backend on
  Windows (`state/private_files.py`).

If the file is world-readable or group-writable, Astron fails closed rather than
quietly tightening permissions you did not authorize it to change.

## What is *not* configurable in this snapshot

These are fixed in code on purpose — changing them means editing the module, not
the YAML:

| Constant | Value | File |
| --- | --- | --- |
| `MAX_READ_ONLY_TOOL_CALLS_PER_TURN` | 4 | `agent/native.py:24` |
| `NativeAgent(max_steps=…, task_timeout_seconds=…)` | 1-12 (default 6) / 1-300 s (default 60) | `agent/native.py:122-126` |
| `MAX_READ_BYTES` / `MAX_LISTED_FILES` / `MAX_TEST_OUTPUT_BYTES` | 65 536 / 512 / 16 384 | `tools/bounded.py:56-59` |
| bounded pytest timeout | 1-60 s (default 15) | `tools/bounded.py:92-93` |
| action step | 1-99 | `tools/bounded.py:179-180` |
| `MAX_OUTPUT_CHARS` / `MAX_READ_CHARS` / `MAX_COMMAND_BYTES` (terminal) | 4 096 / 16 384 / 32 768 | `tools/terminal.py:34-36` |
| Team budgets | `MAX_EXECUTOR_ROUNDS=4`, `MAX_ACTIONS_PER_ROUND=4`, `MAX_TOTAL_ACTIONS=12`, `MAX_TOTAL_TOKENS=32_000` (scheduler default `max_executor_rounds=1`) | `team/scheduler.py:48-55, 286` |
| `RepoTaskBudget` | turns 1-60, wall clock 1-3600 s, calls ≤ turns, output tokens 1-4096 | `agent/repo_task.py:45-53` |
