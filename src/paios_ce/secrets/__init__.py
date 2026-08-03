"""SecretRef interface and backends (Phase 2 SECRETREF_ARCHITECTURE).

Phase 3 implements the abstract SecretRef interface plus two backends:
EnvSecretRef (portable default) and InMemorySecretRef (tests/demo). No secret
value is ever stored in config, logged, serialized, or placed in protocol
envelopes.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .base import (
    SecretRef,
    SecretReferenceUnresolved,
    SecretRedactionError,
    SecretValue,
)
from .env import EnvSecretRef
from .memory import InMemorySecretRef

__all__ = [
    "EnvSecretRef",
    "InMemorySecretRef",
    "SecretRedactionError",
    "SecretRef",
    "SecretReferenceUnresolved",
    "SecretValue",
]
