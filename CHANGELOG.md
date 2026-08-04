# Changelog

All notable changes to PAIOS CE are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for its release tags.

## [Unreleased]

## [0.1.0-rc.1] - 2026-08-04

### Added
- Clean-room public core scaffold implementing the accepted contract.
- Permission engine, redaction engine, audit logger, SecretRef abstraction.
- CLI entry point `paios-ce` with `health`, `validate-config`, `demo`, and
  `run-task` subcommands.
- JSON Schemas for task envelope, action request/result, error envelope,
  audit event, and public/private runtime config.
- publication hygiene: runtime-assembled key-shaped test fixtures
  (no contiguous key-shaped literal in the public tree).
- publication hygiene governance files: `.gitignore`, `.gitattributes`,
  `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `PUBLIC_RELEASE_BOUNDARY.md`,
  `SUPPORT_MATRIX.md`.

### Security
- Redaction invariant enforced at every audit, health, and diagnostics entry
  point. Bare non-pattern secrets require an explicit literal-value mapping.
- No secret value field exists on any public protocol model
  (`TaskEnvelope`, `ActionRequest`, `ActionResult`, `ErrorEnvelope`,
  `AuditEvent`).
- No raw audio, full private path, cookie, authorization header, or owner
  identity detail field exists on any public model.

### Notes
- This is a clean-room re-implementation. No legacy source, no production
  data, no owner PII, and no model weights are included.
