"""Minimal Orchestrator (contract section 15).

Receives a TaskEnvelope, validates config, runs the Risk engine, selects the
Mock Provider, generates the provider request, processes the result, routes
ActionRequests to the Mock Worker, and emits a redacted AuditEvent.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .orchestrator import MinimalOrchestrator, OrchestrationResult

__all__ = ["MinimalOrchestrator", "OrchestrationResult"]
