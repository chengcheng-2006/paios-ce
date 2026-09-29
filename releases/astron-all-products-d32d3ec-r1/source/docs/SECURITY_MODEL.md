# Astron security model

This document describes the implemented security boundary of the Astron
competition revision. It complements, but does not replace, the vulnerability
reporting policy in [`../SECURITY.md`](../SECURITY.md).

## Objective

Astron reduces the authority granted to an untrusted model proposal. It makes
the principal, authorization identity, action scope, durable attempt boundary,
recovery state, and completion decision explicit and testable.

It does not make arbitrary model-generated code safe and does not claim to be
an operating-system sandbox.

## Authorities

| Actor/component | May propose | May authorize | May execute | May reconcile | May mark complete |
| --- | --- | --- | --- | --- | --- |
| Model / Provider | yes | no | no | no | no |
| Trusted caller / principal source | supplies identity context | no | no | no | no |
| Permission Engine | no | yes | no | no | no |
| Bounded Tool Runtime | no | no | admitted actions only | no | no |
| Trusted reconciler | no | no | never reruns action | yes | no |
| Deterministic verifier | no | no | no | no | yes, after acceptance |

## Principal and authorization identity

The runtime receives trusted principal context separately from the
model-controlled action payload. It canonicalizes and binds:

```text
idempotency_key
principal_id
request_fingerprint
security_context_fingerprint
```

The request fingerprint covers the complete normalized action request. The
security-context fingerprint covers the current runtime-granted context. An
exact replay returns the stored full decision. Any key reuse with changed
principal, parameters, request identity, or security context fails closed with
the original record preserved.

## Durable execution boundary

Authorization is not execution evidence. Before invoking a permitted bounded
executor, Astron persists journal intent and then `ATTEMPT_STARTED`. A missing
response after that boundary becomes `UNCERTAIN`, because the side effect may
already have occurred. The runtime never turns uncertainty into implicit retry
eligibility.

A trusted action-specific reconciler observes external facts without rerunning
the action. Only `CONFIRMED_NOT_APPLIED` creates the durable
`RETRY_ELIGIBLE` state, and a later explicit call is still required.

## Bounded tool surface

The competition repository-maintenance path has no arbitrary shell. It admits
only fixed operations with runtime-enforced bounds:

- normalized paths must remain inside one fresh workspace;
- symlink and traversal escape is rejected;
- reads, writes, directory listings, test output, and JSON are size-bounded;
- patching requires an exact expected old value and a unique match;
- pytest uses a fixed interpreter, cwd, target, timeout, and owned child;
- artifact writes use allowlisted locations; and
- multi-call turns may contain only two to four allowlisted read operations.

A mixed read/write batch is rejected atomically before any read executes. A
safe-looking prefix does not authorize an unsafe suffix.

## Completion boundary

The model can see the typed completion-artifact schema, but cannot select an
arbitrary schema or verifier. Syntax validation and a successful action are
intermediate facts. The deterministic verifier independently checks the source
effect, bounded tests, artifact semantics, and forbidden modifications. Only
an accepted verifier record may persist `TASK_COMPLETED`.

## Credential and evidence boundary

The optional OpenAI-compatible Provider is configured with an explicit
environment-variable name, not a literal key. Astron does not enumerate the
environment, load `.env` files, or persist a credential. Durable state and
safe evidence exclude raw headers, model payloads, message content, tool
arguments, file content, and unbounded exceptions.

The repository security scan rejects credential-like and forbidden private
content. Error metadata is length-bounded and credential-redacted.

## Durable private state

On POSIX systems, new durable state files and parent directories are restricted
and verified with owner-only modes. On Windows, privacy is established and
verified using platform access-control semantics rather than treating
synthetic POSIX mode bits as ACL proof. If privacy cannot be established or
verified, the state store fails closed; it does not silently repair an existing
unknown file policy.

SQLite uses foreign keys, WAL journaling, `synchronous=FULL`, a bounded busy
timeout, and immediate transactions for security-critical serialization. These
choices improve local durability but do not protect against a compromised OS,
storage stack, or Python runtime.

## Fail-closed examples

- unknown, critical, arbitrary-shell, and administrator actions are blocked;
- missing capability or out-of-scope filesystem/network targets are blocked;
- same-key parameter/principal/context mismatch is blocked;
- store corruption, unsupported schema, lock timeout, or unverifiable private
  file policy is a typed state-store failure with no in-memory fallback;
- post-attempt uncertainty requires reconciliation and does not invoke the
  executor; and
- malformed model output, unsafe tool batches, bad artifacts, or failed tests
  cannot produce verified completion.

## Threats outside the claim

Astron does not claim to solve:

- malicious OS administrators or a compromised Python interpreter;
- arbitrary untrusted-code containment;
- supply-chain compromise outside the reviewed dependency set;
- universal exactly-once delivery across external systems;
- production multi-user or network-perimeter isolation;
- prompt injection in arbitrary future adapters; or
- correctness of a third-party model or Provider service.

## Reporting

Do not publish suspected vulnerabilities in a public issue. Follow
[`../SECURITY.md`](../SECURITY.md) and use the repository's private security
reporting channel.
