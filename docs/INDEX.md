# PAIOS CE Documentation

Welcome to PAIOS CE documentation.

## Overview

PAIOS CE is a clean-room public core scaffold for a privacy-preserving personal AI orchestrator.

## Documents

- [README](../README.md) - Project overview and quick start
- [Security Policy](../SECURITY.md) - Security defaults and reporting
- [Contributing](../CONTRIBUTING.md) - How to contribute
- [Support Matrix](../SUPPORT_MATRIX.md) - Supported versions and components
- [Changelog](../CHANGELOG.md) - Version history
- [Public Release Boundary](../PUBLIC_RELEASE_BOUNDARY.md) - Scope and guarantees

## Architecture

PAIOS CE follows a modular architecture:

- **Config** - Public/private configuration with safe defaults
- **Secrets** - SecretRef indirection (values never stored)
- **Protocols** - TaskEnvelope, ActionRequest, AuditEvent models
- **Permissions** - Deny-by-default permission engine
- **Providers** - Provider contracts (Mock Provider implemented)
- **Channels** - Channel contracts (CLI implemented)
- **Routing** - Minimal router to Mock Provider
- **Workers** - Worker contracts (Mock Worker implemented)
- **Audit** - Redacted audit logger
- **Health** - Component health diagnostics

## Quick Start

```bash
# Install for development
pip install -e ".[dev]"

# Run demo
paios-ce demo

# Run tests
pytest

# Check health
paios-ce health
```

## Security

- Never include real secrets or production data
- Use placeholders in all examples
- Follow the deny-by-default permission model
- Report security issues privately