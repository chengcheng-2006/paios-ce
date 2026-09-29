# Astron — Security Policy

## Reporting

This project is a release candidate. Do not open public issues for
vulnerabilities. When the public repository is launched, use GitHub's private
vulnerability-reporting channel (Security Advisories) if it is enabled for the
repository. Do not disclose exploitable details in a public issue.

### What to include in a report

- affected component and version or commit;
- reproducible steps (placeholders only);
- expected vs actual behavior;
- impact assessment;
- environment (OS, Python version, optional speech backend if relevant);
- minimal sanitized evidence.

## Security model scope

Astron is an execution-control reference runtime evolved from the public PAIOS
CE baseline. It does not claim to be a
universal sandbox: it does not promise zero-risk execution, complete
isolation, or absolute prevention of every failure mode. Its explicit
fail-closed gate is described in detail in
docs/SECURITY_MODEL.md and in the README security-boundary diagram.

## Security defaults (frozen)

- **Loopback only by default.** All listeners default to `127.0.0.1`; `public_bind` is
  `false`. LAN/public exposure requires explicit opt-in plus a risk acknowledgment.
- **DM-only, group execution off by default.** `dm_only=true`, `group_execution=false`.
- **Owner allowlist required.** `owner_allowlist_required=true`; owner-only actions
  (admin elevation, credential rotation, destructive operations, financial external
  writes) require an owner principal.
- **High-risk confirmation enabled.** HIGH-risk actions require explicit confirmation;
  CRITICAL actions are hard-blocked in the current release candidate; arbitrary shell
  and admin elevation are hard-blocked.
- **Deny-by-default permission model.** Every worker starts with zero capabilities; any
  capability must be explicitly granted and scoped.
- **SecretRef only for credentials.** Secret values are never stored in config, never in
  logs, never in error messages, never in audit events, never in TaskEnvelope, never
  persisted by a frontend, never hashed into public reports. Only the redacted reference
  `<backend>:<short_id>` is recorded.
- **No raw audio / no cloud ASR by default.** `raw_audio_storage=false`,
  `cloud_asr=opt_in_only`, `temp_audio_delete=true`.
- **No live integrations in this release candidate.** Mock Provider only; no real
  Provider, Channel, Speech, or Shell execution; no network writes; no browser
  automation; no production database; no remote server; no public internet binding.

## Supported capabilities

The current release candidate implements `EXPERIMENTAL` Mock Provider and
CLI. No capability is labeled SUPPORTED until it passes its acceptance
test on a clean machine with end-to-end evidence. See `SUPPORT_MATRIX.md`
for the authoritative status table.

## Secrets and PII

- Placeholders only in all examples: `not-a-valid-provider-token`, `example.invalid`,
  `127.0.0.1`, `<USER_HOME>`.
- Real secrets, tokens, cookies, audio, chat records, browser profiles, DPAPI stores,
  `.env` files, and production logs must never appear in this repository.

## Clean-room boundary

- All source is `NEWLY_WRITTEN_FROM_PUBLIC_CONTRACTS`; `LEGACY_CODE_COPIED = NO`.
- No `.git` inside published artifacts. The source is maintained in a clean-room
  Git repository. Repository visibility and release actions are governed
  separately by the Owner.
