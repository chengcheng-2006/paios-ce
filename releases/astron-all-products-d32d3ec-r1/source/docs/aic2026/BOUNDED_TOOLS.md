# Astron Phase 3: Bounded Tool Contract

## Authority boundary

Phase 3 exposes a deliberately small, local repository-maintenance toolset.
There is no generic shell, command runner, browser, UI automation, package
installer, network tool, worker launcher, subprocess API for model input, or
multi-agent capability.

Every proposed tool call is converted by trusted code into an `ActionRequest`
with a fixed principal, fixed capability, fixed scope class, task-local
idempotency key, and bounded timeout. It then travels through:

```text
proposal -> ActionRequest -> Permission Engine -> durable authorization
-> journal -> ATTEMPT_STARTED -> trusted executor -> terminal journal state
```

A model cannot provide its own principal, capability, filesystem root,
permission, subprocess command, or completion state.

## Filesystem rules

A tool receives one concrete workspace root created from the fixture. Paths
are relative POSIX-style paths only. Absolute paths, empty paths, `..`
segments, files outside the root, non-regular target files, and symlinks in a
target or its ancestors are rejected. Canonical resolution is checked against
the root before use; an in-root spelling is not sufficient proof of scope.

Reads are UTF-8 text only and size bounded. Directory listing is deterministic
and bounded. A patch supplies the expected old text; it must match exactly
once before the new content is written through an atomic replacement. An
artifact write is limited to the task artifact directory and does not modify
the fixture's source or test files.

| Tool | Capability and scope | Bound |
| --- | --- | --- |
| `workspace.list_files` | `WORKSPACE_READ`, workspace read | deterministic file-count limit |
| `workspace.read_text` | `WORKSPACE_READ`, workspace read | UTF-8 and byte limit |
| `workspace.patch_text` | `WORKSPACE_WRITE`, workspace read/write | one exact precondition and atomic replace |
| `workspace.write_artifact` | `ARTIFACT_WRITE`, workspace write | artifact directory and byte limit; V4 completion contract is Agent-visible |
| `validate.json` | `WORKSPACE_READ`, workspace read | bounded syntax check or trusted named semantic schema |
| `validate.file` | `WORKSPACE_READ`, workspace read | regular-file and size checks |
| `test.run_pytest_bounded` | `TEST_RUN_PYTEST`, workspace read | fixed interpreter, fixed cwd and allowlisted pytest target |

The list is allowlisted exactly. Any other tool name is denied before an
executor is reached.

`validate.json` remains syntax-only when no `schema_id` is supplied. Its only
named semantic mode is the trusted registry entry
`maintenance_completion.v1`, fixed to
`.astron-artifacts/change_summary.json` and validated against the runtime's
trusted task ID. A model cannot provide a schema path, register a schema, or
substitute another task identity. Syntax or semantic validation never writes
the artifact and never replaces the deterministic completion verifier.

## Bounded pytest

`test.run_pytest_bounded` is not an arbitrary process capability. Trusted
code invokes only `[trusted_python, "-m", "pytest", allowed_target, "-q"]`
with `shell=False`, the fixed workspace as cwd, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
a fixed output cap, and a task-defined timeout. User/model flags, arbitrary
environment injection, plugin injection, alternate cwd, test selectors,
executables, and shell syntax are unavailable.

On a timeout the runtime acts only on the exact child PID it created, first
terminating and then, if necessary, killing that identified child after a
bounded wait. It never uses fuzzy process matching, `pkill`, or `killall`.
This is containment by a narrow interface, **not** an OS sandbox:

```text
UNTRUSTED_CODE_SANDBOX=NO
```

The fixture and its tests are trusted competition inputs. They must not be
treated as arbitrary untrusted code.

## Crash and recovery

If a bounded mutating tool raises after `ATTEMPT_STARTED`, the durable runtime
records `UNCERTAIN`. A restart does not execute it again; it requires the
same evidence-based reconciliation discipline as Phase 2. Phase 3 does not
claim exactly-once behavior for filesystem or test subprocess effects.
