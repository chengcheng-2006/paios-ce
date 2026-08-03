"""Configuration models and loader (Phase 2 CONFIGURATION_MODEL).

Precedence (highest wins): CLI flags -> process environment -> private local
config -> public project config -> built-in safe defaults.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .loader import ConfigLoadError, ConfigLoader, load_runtime
from .models import (
    AuditConfig,
    CapabilitiesConfig,
    DefaultsConfig,
    PrivateConfig,
    PublicConfig,
    RuntimeConfig,
    SecretRefDecl,
)

__all__ = [
    "AuditConfig",
    "CapabilitiesConfig",
    "ConfigLoadError",
    "ConfigLoader",
    "DefaultsConfig",
    "PrivateConfig",
    "PublicConfig",
    "RuntimeConfig",
    "SecretRefDecl",
    "load_runtime",
]
