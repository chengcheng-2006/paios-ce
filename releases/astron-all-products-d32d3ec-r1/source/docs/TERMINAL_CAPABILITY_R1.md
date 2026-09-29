# Terminal Capability R1

## Scope and authority

Terminal R1 adds a persistent, macOS-first terminal capability to Astron
Single.  It is an execution capability, not a benchmark result.  The worktree
was created from the verified stable Astron Single source at
`ca036a88efe3e8203077cd37b1681f03fa19132b` on
`aic/2026-benchmark-pilot-single-r3`; the implementation branch is
`feature/terminal-capability-r1`.

This document records implementation and local deterministic evidence only.
It makes no SWE-bench, DeepSeek, or model-performance claim.

## Model-visible tools

The Terminal R1 registry adds these bounded function tools while retaining the
existing native file and validation tools:

| Tool | Bounded request | Result semantics |
| --- | --- | --- |
| `terminal_open` | optional workspace-relative `cwd`, bounded `env` map | terminal id, resolved cwd, shell, status |
| `terminal_send` | owned terminal id, text command, background flag, 1–60 second wait | bounded/redacted output, exit code, running and timeout facts |
| `terminal_read` | owned terminal id and 1–16,384 character read bound | new bounded/redacted output and process state |
| `terminal_signal` | owned terminal id and `SIGINT` only | signal receipt and running state |
| `terminal_close` | owned terminal id | process-group cleanup outcome |
| `terminal_list` | no model-controlled arguments | caller-owned session metadata only |

The host implementation uses `/bin/zsh` under a PTY on macOS.  A trusted,
delimiter-framed dispatcher evaluates each supplied command in the same shell
process, so `cd`, exported environment variables, aliases, and jobs persist
across calls.  The dispatcher is non-prompting and suppresses typed-command
echo; this avoids reflecting a command containing a secret back into model
context.

Windows PowerShell is not implemented in R1.  The service has an explicit
backend boundary and reports unavailable rather than silently substituting a
different shell on an unsupported platform.

## Governance path

No model response has a direct process path.  A terminal proposal follows:

```text
LLM tool call
  -> Native/Terminal-enabled registry
  -> schema and terminal policy validation
  -> PermissionEngine capability, filesystem, network, and process-scope checks
  -> DurableActionRuntime authorization + attempt journal
  -> redacted terminal action journal correlation record
  -> trusted TerminalService PTY dispatch
  -> bounded/redacted Tool Result
  -> role=tool message on the next model turn
```

`terminal_*` operations are classified as `TERMINAL_CONTROL`, a separately
admitted policy class.  They do not use the legacy arbitrary
`PROCESS_EXEC`/shell route, which remains hard-blocked.  The permission engine
requires an explicit terminal capability, `terminal_workspace` scope, and
`terminal_session` process scope.  The durable state store records the
authorization identity and action lifecycle before the executor is invoked.

The redacted sidecar journal has a start and result record for every dispatched
terminal action.  It contains the logical action id, tool name, trusted agent
owner, terminal id, request fingerprint, decision, start/result facts, and a
safe error code.  It intentionally does not store command text, environment
values, or output.

## Ownership, replay, and cleanup

Every service access resolves a terminal id and compares its owner with the
trusted caller identity.  A different owner cannot send, read, signal, or
close a known id, and `terminal_list` returns only its own sessions.

The logical tool-call identity determines both the durable idempotency key and
the newly opened terminal id.  An exact re-submission resolves to the existing
durable journal and does not dispatch a second shell command.  If an exception
occurs after `ATTEMPT_STARTED`, `DurableActionRuntime` marks the action
`UNCERTAIN`; a repeat returns `needs_reconciliation` without re-dispatching.

Closing a terminal targets its dedicated process group.  It sends `SIGTERM`,
then escalates to `SIGKILL` only if needed.  This stops foreground and
background children rather than waiting for a shell-level `exit` to complete.
An exit code caused by this intentional cleanup is recorded as successful
`terminal_close`, not as a failed command.

## Workspace and command policy

`cwd` is resolved before terminal creation and must be an existing,
non-symlink descendant of the configured workspace.  Relative traversal,
absolute paths outside the root, invalid environment variable names, NULs,
and oversized inputs are rejected.  Terminal log and journal roots are
explicitly refused if they would be placed inside the task workspace, keeping
SWE task diffs free of runtime bookkeeping.

R1 has explicit policy hooks that deny administrator/elevation and destructive
syntax (`sudo`, `doas`, `launchctl`, shutdown/reboot, recursive-force remove)
and network clients (`curl`, `wget`, `nc`, `ssh`, `scp`, `ftp`) by default.
The policy does not claim complete semantic analysis of arbitrary shell text.

`WORKSPACE_BOUNDARY_MODE=CWD_NORMALIZATION_AND_POLICY_GUARDS`

`HOST_SANDBOX_LIMITATION=R1 does not impose an OS-level filesystem or network sandbox on arbitrary commands once a host shell is admitted. Docker task containers remain the required strong isolation boundary for future SWE-bench runs.`

## Output and secrets

Model-visible output is deterministically bounded to `MAX_OUTPUT_CHARS=4096`.
Oversized output uses a head/tail representation and sets `truncated=true`
with an explicit marker.  Full *redacted* session output is retained in the
out-of-workspace terminal log root.

Environment values whose names indicate credentials (`SECRET`, `TOKEN`,
`PASSWORD`, `API_KEY`, or `CREDENTIAL`) are never returned by list operations
and are replaced with `***REDACTED***` in terminal output and log material.
Commands, complete environment maps, and exception text are not written to the
terminal action journal.  R1 starts a minimal process environment rather than
implicitly inheriting host API credentials.

## Deterministic certification

`tests/terminal/test_terminal_r1.py` contains 28 passing R1 tests.  They cover
the required 22 cases plus durable-uncertain replay, governed cross-agent
ownership, dangerous/network policy denials, input/schema bounds, and log-root
isolation.  The direct tool smoke and synthetic local-provider agent-loop smoke
are also independently emitted by `qa/terminal_r1_smoke.py`.

The test suite intentionally uses no external model and no API key.  See
`qa/TERMINAL_R1_CERTIFICATION.json` and
`qa/TERMINAL_R1_TEST_REPORT.md` for the dated receipt and coverage data.
