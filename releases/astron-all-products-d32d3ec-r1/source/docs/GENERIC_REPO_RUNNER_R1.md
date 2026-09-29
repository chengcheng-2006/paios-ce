# Generic Repo Task Runner R1

`RepoTaskRunner` is Astron Single's governed compatibility layer for one
prepared repository task. It accepts a public problem statement, a clean
already-checked-out Git repository, bounded runtime settings, optional public
metadata, and the frozen native tool surface. It deliberately has no
SWE-bench-specific input, task-id dispatch, grader fixture, reference patch,
or correctness decision.

Each task has a unique runtime directory, durable state database, terminal-log
root, owner identity, messages, and Terminal R1 sessions. The runner rejects a
dirty checkout before any provider call and captures its trusted base commit,
post-run Git status, `git diff`, changed tracked paths, trajectory, bounded
usage, latency, final answer, and explicit runtime status.

Model text such as `done`, `fixed`, or `completed` maps only to
`AGENT_STOPPED`. `RepoTaskRunner` never returns a solved/SWE-success verdict;
an external evaluator remains the authority. Budget exhaustion is recorded as
`BUDGET_EXHAUSTED` using independent turn, provider-call, wall-clock, and
output-token ceilings.

The runner supports Astron's existing bounded file/pytest tools and the frozen
Terminal R1 family. It does not add an oracle, a reference-test reader, a
solution search capability, or a patch-application shortcut. Terminal replay
identity is the model's logical tool-call id, preventing a repeat from opening
or dispatching a second terminal operation.

The R1 QA suite uses only self-authored synthetic repositories. It contains 18
deterministic tests covering mutation tracking, multi-turn feedback, budget,
dirty-workspace rejection, cross-task isolation, terminal timeout/replay, and
redaction; no SWE-bench instance was exposed during development.
