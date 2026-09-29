# FAQ (defence questions)

> 版本与证据边界：本文介绍产品快照 `d32d3ec1bc49a78d0b14aabb6bf0daf79d3f4d88`；如提及 R2 评测数字，其测量运行来自 `13ee283ce8b6121af14b1bf0f1f9deefe1484cf2`。d32d3ec 本身没有正式模型实跑证据。


Answers a reviewer or a new maintainer can check against the code. Project-level
user FAQ material also exists upstream in `../../../source/docs/FAQ.md`; this page
covers the harder questions.

**1. Isn't this just a chatbot wrapper?**
No. There is no chat loop, no channel, no UI. Astron is the layer *underneath* a
proposal loop: it decides whether a proposed action may execute, records what
happened, and decides whether the task is complete. Live channels are labelled
`PLANNED` in `SUPPORT_MATRIX.md` and are skeletons.

**2. Where exactly is the model/harness division of labour?**
Model side: `providers/openai_compatible.py:206` returns tool calls as data.
Harness side: `tools/bounded.py` normalizes them into an `ActionRequest` whose
scopes the model never chose; `permissions/engine.py` decides;
`runtime/durable_runtime.py` orders and persists; `agent/verifier.py` completes.
The principal is passed by trusted code (`cli/main.py:238-245`), and no JSON field
named `owner_identity`/`actor`/`user` can select it.

**3. How is permission actually controlled? Isn't a whitelist the same thing every
agent framework has?**
Three differences. (a) It is deny-by-default with named capabilities; a worker
starts from an empty set. (b) An unregistered operation name is *explicitly
rejected* as `UNKNOWN_ACTION` before any capability, approval or scope check —
so a hallucinated name cannot be coerced into a known class. (c) The decision is
persisted as durable state bound to an identity
(`key + principal + request fingerprint + security-context fingerprint`), so a
replay restores the original decision and a mismatch is blocked with
`E_IDEMPOTENCY_KEY_REUSE_MISMATCH`.

**4. What does recovery actually guarantee — and what does it not?**
It guarantees that after a restart you can read what was authorized, attempted and
settled, and that an action whose outcome is unknowable is classified
`NEEDS_RECONCILIATION` rather than silently retried. It does **not** guarantee
exactly-once delivery against an arbitrary external system: only an action-specific
trusted `Reconciler` can settle `UNCERTAIN`, and if you cannot write one, that
action type should not be enabled. `rollback_supported` is `False` for every
operation in this snapshot.

**5. Is Team mode stronger than Single?**
Not claimed. Team is the *narrower* authority model — per-role tool profiles, a
mailbox with fixed routes, and a gate that raises unless the `VERIFIER` role
requests completion. It is also less finished: no CLI entry, excluded from the
wheel by `pyproject.toml`, default `max_executor_rounds = 1`, a `team/feedback.py`
dead-code defect, and in the R2 history it was the arm with 0 capability passes
plus one `TEAM_BLOCKED` run. It is shipped as experimental and labelled that way
throughout.

**6. How do I add a new tool, and why does it take five files?**
Schema in `agent/native.py`, operation + capability in `tools/bounded.py`,
parameter allowlist in `_normalize_parameters`, handler in `_execute_request`,
risk class in `permissions/policy.py`. That breadth is the design: a tool is a
change to what the model can ask for, what the runtime will accept, and what the
policy will classify — collapsing those into one decorator is how you end up with
a "restricted" tool that runs arbitrary commands. `docs/DEVELOPER_GUIDE.md` §3
lists the places and the two rules that must survive.

**7. Which capabilities are genuinely supported today?**
The ones in `README.md`'s capability table: authorization with hard blocks,
durable action lifecycle, `UNCERTAIN` + reconciliation, the bounded tool surface,
seven governed workspace/test tools plus six POSIX terminal tools, verified
completion for one fixture family, `RepoTaskRunner` for a generic governed repo
task, redacted audit, public/private/env config precedence, optional local ASR.
Everything in `Scaffold` rows (`orchestrator`, `routing`, `workers`, `channels`)
is interface material, and is not presented as a feature.

**8. What is not supported?**
A general repository verifier; live channels; microphone or streaming speech;
group execution; remote execution; encrypted state; a scheduler, queue, metrics or
alerting; an audit-log writer (the default sink is in memory); Windows terminal
support; a Team resume path; multi-agent networks; OS-level containment; any
undo/compensation semantics. Full list in `docs/SECURITY_AND_LIMITATIONS.md`.

**9. Where is the cost in this design?**
Three places. Latency and code volume: every action writes at least two durable
rows before the effect, so throughput is lower than an in-memory loop — the
bounded pytest timeout is 15 s default against a 60 s ceiling, which is the scale
of the overhead. Model cost: read-only calls may batch (max 4 per turn) but every
mutating step burns its own turn, so a seven-action task costs at least five
model turns; `NativeAgent` caps that at 6 steps and 60 s by default. Human cost:
`UNCERTAIN` is allowed to stall, which is operationally correct and occasionally
annoying — you resolve it with a reconciler or by hand, not by rerunning.

**10. If offline tests pass, why not claim it is safe?**
Because the tests assert contracts in a deterministic environment: an unknown name
is blocked, a crash is classified, a redactor refuses a dirty event. They do not
exercise a hostile provider, a multi-host SQLite writer, a compromised interpreter,
or real latency pressure. `PUBLIC_RELEASE_BOUNDARY.md` states explicitly that no
production readiness, SLA or fitness claim is made, and this package repeats it.

**11. Didn't you measure whether Astron helps?**
Yes, and the measurement did not support the claim. R2: 120 formal runs, three arms
of 40, one task family, on runtime `13ee283` with DeepSeek `deepseek-v4-flash`
(alias-only, backend not pinned). The capability subset was a floor effect —
`0/72`, with all three arms at zero — and 23 provider errors censored the arms
differentially (Direct 22.5 %, Single 35.0 %, Team 0 %). No ordering follows from
that. The stress subset (2/16, 4/16, 0/16 over only 8 unique cases) would be noise
to rank on. `docs/EVALUATION_SUMMARY.md` keeps observed facts, measurement validity
and inference visibly separate, and lists which safety flags were not comparable.

**12. So what does the research add to the product?**
Nothing yet, and the shipped code does not pretend otherwise. R3 is development-set
calibration; its pre-registration puts formal execution and any final-holdout model
exposure out of scope, freezes the Astron core, and lists the components R2
identified as missing (executor/binding layer, ledger, resume, control-plane state
machine) as things to validate *before* a final holdout. The R3 harness and task
bank are evaluation engineering, not Astron, and are deliberately not in this
package.

**13. Why is the import path `paios_ce` and the CLI `astron`?**
Same codebase, two identities: `paios_ce` is the historical package (upstream repo
`chengcheng-2006/paios-ce`), Astron is the competition identity built on it. The
import path and the `paios-ce` console alias are kept for compatibility; a global
rename would break every existing import for no behavioural gain. Provenance is
recorded in `docs/aic2026/BASELINE.md` and `docs/aic2026/COMPETITION_SCOPE.md`.

**14. Is this package a release?**
No. It is a delivery assembly of the committed snapshot `d32d3ec`, not a new
version or an official release. This copy is uploaded on a dedicated GitHub
branch; no GitHub Release or tag is created. `pyproject.toml` still says
`0.1.0rc2`, and upstream documents disagree among themselves about `rc.1` versus
`rc.2`, which is recorded as a known defect rather than silently "fixed".

**15. Can I run everything right now?**
On macOS or Linux with Python ≥ 3.11: `pip install -e ".[dev]"` and the three demo
scripts in `examples/demos/` plus `python -m pytest -ra -q` run with no key, no
network and no model weights. The one thing you cannot reproduce from this package
is the R2 live numbers — they required a real DeepSeek credential, which is not
bundled and not required for anything documented here.
