"""EnvSecretRef — portable default backend (Phase 2 section 4.1).

The config holds only the environment variable NAME; the value is read from
the process environment at resolve time and never stored in config, logs, or
envelopes.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import os

from .base import SecretReferenceUnresolved, SecretRef, SecretValue


class EnvSecretRef(SecretRef):
    """Resolves a secret from an environment variable."""

    backend_id = "env"

    def __init__(self, env_var: str) -> None:
        super().__init__(ref_id=env_var)
        if not env_var or not isinstance(env_var, str):
            raise ValueError("env_var must be a non-empty string")
        self._env_var = env_var

    @property
    def env_var(self) -> str:
        return self._env_var

    def exists(self) -> bool:
        value = os.environ.get(self._env_var)
        return value is not None and value != ""

    def resolve(self) -> SecretValue:
        value = os.environ.get(self._env_var)
        if value is None or value == "":
            # Message contains only the env var name and backend id, never the value.
            raise SecretReferenceUnresolved(
                f"env:{self._env_var} is not set or empty in this process environment"
            )
        return SecretValue(value)

    def redact(self) -> str:
        return f"{self.backend_id}:{self._env_var}"
