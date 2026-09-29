"""InMemorySecretRef — in-process test/demo backend (NOT a persistent store).

Holds a value only for the lifetime of the object, in memory, never written to
disk, never logged, never serialized. Intended for unit tests and the local
demo. NOT a production secret backend.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from .base import SecretReferenceUnresolved, SecretRef, SecretValue


class InMemorySecretRef(SecretRef):
    """Resolves a secret from a value injected in-process (test/demo only)."""

    backend_id = "in_memory"

    def __init__(self, value: str, ref_id: str = "local_only") -> None:
        super().__init__(ref_id=ref_id)
        self._value = value

    def exists(self) -> bool:
        return self._value != ""

    def resolve(self) -> SecretValue:
        if self._value == "":
            raise SecretReferenceUnresolved(
                f"in_memory:{self._ref_id} holds no value (empty)"
            )
        return SecretValue(self._value)

    def redact(self) -> str:
        return f"{self.backend_id}:{self._ref_id}"
