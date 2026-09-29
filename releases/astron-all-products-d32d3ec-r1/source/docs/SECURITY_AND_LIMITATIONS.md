# Security model and real limitations

Two documents, deliberately separated:

* [`SECURITY_MODEL.md`](SECURITY_MODEL.md) is the upstream design: which
  component holds which authority, the credential boundary, per-OS state privacy,
  the SQLite durability settings and the fail-closed examples. It is accurate for
  this snapshot and is the place to read the *model*.
* this file is the **limits**: what the code in snapshot `d32d3ec` does not
  guarantee, where a bound is easy to mistake for a protection, and what a
  reviewer should not conclude from the tests.

## What is enforced in code

| Guarantee | Where | Honest scope |
| --- | --- | --- |
| Deny-by-default | `permissions/engine.py:501` — capabilities must be granted by name; every worker starts from an empty set | the shipped compositions grant the whole tool registry to one principal (below) |
| Hard blocks | `permissions/engine.py:284` — unknown action, arbitrary shell keyword, admin elevation, process exec, financial, identity, CRITICAL | a *name/pattern* gate: `execution_attempted=false`, but it only blocks what Astron itself dispatches |
| Unknown action ⇒ explicit reject | `policy.classify` returns `UNKNOWN_ACTION`, blocked with `E_UNKNOWN_ACTION` before any policy, capability or approval check | prevents coercion of unregistered names into a known class |
| Trusted principal | `PrincipalContext` is passed by the caller; `cli/main.py:238-245` documents that no JSON field may select it | the CLI's default principals are placeholders; you must supply real ones |
| Scope containment | `ScopeGuard` class comparison + `_relative_path`/`_safe_path` symlink and escape checks | class-based, not inode-based: the workspace must be a real directory tree you own |
| Durable authorization identity | `permissions/engine.py:345, 436` + `state/durable.py:617` | replay of a *decision*; not proof that an action ran |
| Attempt-before-effect ordering | `runtime/durable_runtime.py:71-152` | within one process's correct use of the API |
| No blind retry of `UNCERTAIN` | `runtime/durable_runtime.py:102-105`, `state/durable.py:864` | requires a caller-supplied, action-specific `Reconciler` |
| Redaction | `audit/redact.py` — forbidden keys, secret-shaped values, path hints, depth/byte caps, `RedactionNotGuaranteedError` | redaction of what the logger is *given*; it is not a DLP layer |
| Owner-private state file | `state/private_files.py` (POSIX `0o600`, Windows ACL/SDDL) | file permissions, not encryption |

## Limits a reviewer will otherwise miss

**Bounded execution is not a sandbox.** `test.run_pytest_bounded` runs
`python -m pytest tests -q` as a real subprocess in the workspace, with a
minimal environment (`PATH`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`) and plugin
autoload off (`tools/bounded.py:420-448`). Anything the fixture's own test files
do — open files, listen on a socket, spawn threads — is performed by your real
Python interpreter with your real user's permissions. Astron bounds the command,
the timeout and the output; it does not confine the process. "Restricted test
execution" must never be described as read-only execution or as an OS sandbox.

**The terminal capability is a real shell.** `terminal_open` starts
`/bin/zsh -dfc <dispatcher>` (or `/bin/sh`) attached to a pty, and later commands
are `eval`-ed inside it (`tools/terminal.py:236-256`). The controls are: cwd
normalization inside the workspace; a regex blocklist for administrator and
destructive syntax; network-capable command syntax denied unless
`allow_network_commands=True`; per-session owner; `SIGINT` only; output capped at
`MAX_OUTPUT_CHARS=4096` per read and secret-redacted; a raw transcript written
under `.astron-terminal-logs/` (mode `0700`). Two consequences worth stating
plainly: model-supplied `env` entries are merged *over* the session defaults
(sixty-four items, 8 KiB each — `PATH` included), and the blocklist is pattern
matching, not an ability check. The module says so itself: *"It is intentionally
not described as an OS sandbox. … Container isolation remains the future
SWE-bench boundary."* POSIX only: `os.openpty` means no Windows implementation.

**Capability granularity exists but is not exercised by the shipped agent.**
`BoundedToolRuntime` grants `WORKSPACE_READ`, `WORKSPACE_WRITE`, `ARTIFACT_WRITE`
and `TEST_RUN_PYTEST` to a single principal
(`tools/bounded.py:104-113`), with an empty `owner_allowlist`. So within
`maintenance-demo` the engine's job is normalization, risk classification, replay
identity and journaling — not "which of these four can this agent have".
Team is where per-role narrowing is real (`SUPERVISOR` gets
`capabilities=frozenset()`; auditor and verifier get read+test only,
`team/adapters/tool_authority.py:77-119`). Treat role-scoped authority as the
experimental part, not as a shipped authorization model for Single.

**File writes are text-only, with newline and encoding side effects.** The
workspace tools read with `read_text(encoding="utf-8")` and write in text mode
(`tools/bounded.py:451-465`). A CRLF file is read with translated newlines and
rewritten with the platform's line ending, so a one-line patch to a CRLF file can
change every line. Non-UTF-8 or binary files are rejected outright. The patch
precondition is exact single-match: `old.count(expected) != 1` raises, which is a
safety property, not a convenience.

**Reads and listings are bounded in bytes and counts.**
`MAX_READ_BYTES=65_536` per read/patch/validation, `MAX_LISTED_FILES=512`,
`MAX_TEST_OUTPUT_BYTES=16_384`, `MAX_ARTIFACT_BYTES=16_384`,
`max_summary_characters=256`, tool arguments ≤ 16 384 bytes, agent step 1-99,
tool result context truncated to 2 048 characters. A large repository therefore
cannot be inspected in one call, and a truncated test output is exactly that:
truncated. Never read a truncation as a model-capability or safety result.

**Artifact creation can create directories.** `workspace.write_artifact` is
confined to `.astron-artifacts/`, but `_atomic_write` does
`path.parent.mkdir(mode=0o700, parents=True)`, so nested directories appear
inside that subtree. The verifier whitelists the whole `.astron-artifacts` tree,
so anything in it is accepted as "an artifact" as long as the required file is
valid. The bound is on path, size and the completion contract — not on directory
depth.

**`rollback_supported` is `False` everywhere.** Nothing in this snapshot undoes a
successful action. Compensation, if you need it, is your application's job.

**A completed task is a statement about one fixture.** `MaintenanceVerifier`
documents itself as a *"Fixed oracle for a fresh trusted fixture, not a general
repo verifier"*, and `_changed_or_unexpected_paths` compares against hard-coded
expected file contents. The governance machinery is general; the packaged
completion criterion is not. `RepoTaskRunner` deliberately returns
`AGENT_STOPPED`/`BUDGET_EXHAUSTED` and no verdict at all.

**Offline green is not production safety.** 546 tests pass with no network and no
credential, which shows the contracts hold in a deterministic environment. It
does not show resistance to a hostile provider, a race against another writer of
the same SQLite file across machines, a compromised Python environment, or a
provider that returns adversarially large or slow responses under real load.
`PUBLIC_RELEASE_BOUNDARY.md` states plainly that no production readiness, SLA or
fitness claim is made.

## Credentials

Only `env`-backed SecretRefs are exercised. The provider takes the *name* of an
environment variable, validates it as a name, and reads it lazily. Endpoints must
be absolute http(s) URLs with no credentials, query or fragment. Config templates
use `example.invalid` placeholders. No credential value is written to the durable
store, to audit events, or to `provider_diagnostics`.

## Not implemented

Live channels (skeletons only); live/microphone speech; group execution (default
off, needs acknowledgment); remote execution (default false); Hermes/OpenClaw
integration; workers other than the mock; any scheduler or service supervisor;
encryption of the state file; a general repository verifier; a resume path for
Team; an audit-log sink.

## Known defects present in the snapshot, kept unmodified

* `team/feedback.py:37` `assert_no_hidden_material` references `Mapping` and
  `FORBIDDEN_CONTEXT_KEYS`, neither of which it imports — calling it raises
  `NameError`. Nothing calls it; the benchmark layer has its own copy.
* `providers/__init__.py` claims only the Mock Provider is implemented; the
  OpenAI-compatible adapter is real and CLI-reachable. Stale upstream comment.
* `SUPPORT_MATRIX.md` predates the terminal and generic-runner work: it has no
  row for `terminal_*`, `RepoTaskRunner` or `team/`, lists `maintenance-baseline`
  in neither its CLI row nor the README, records `452 passed + 1 skip` where the
  current suite reports a larger count, and its version prose still mentions
  `v0.1.0-rc.1` while `pyproject.toml` says `0.1.0rc2`.
* `tests/unit/test_speech_policy.py:117` skips where the filesystem cannot create
  junctions.
* `python -m paios_ce.tools.validate_schemas --schemas schemas` is CWD-relative
  and fails from an installed package outside the repository root.

Fixing these is a code decision for the Owner; silently rewriting them inside a
delivery package would misrepresent the snapshot, so they are documented instead.

## Reporting

Upstream `SECURITY.md` describes the reporting channel and the disclosure
expectations. It labels the whole tree a release candidate and repeats the
non-claim that matters most: Astron "does not claim to be a universal sandbox".
