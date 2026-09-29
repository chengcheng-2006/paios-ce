"""Health and diagnostics (health and diagnostics contract).

Outputs component / status / reason / safe_details. Never outputs secrets,
full environment, real tokens, or user private paths. Never auto-networks.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .health import ComponentHealth, diagnostics, health_check

__all__ = ["ComponentHealth", "diagnostics", "health_check"]
