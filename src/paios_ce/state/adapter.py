"""State adapter interface (Phase 3 OPTIONAL).

SQLiteStateAdapterSkeleton declares the interface only; it does NOT open a
real SQLite database, does NOT persist anything, and requires no credentials.
NoopStateAdapter is a fake-local adapter used by tests/demo.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional


class StateAdapter(abc.ABC):
    """Key-value state adapter interface (optional component)."""

    @abc.abstractmethod
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Return a stored value or None."""

    @abc.abstractmethod
    def put(self, key: str, value: Dict[str, Any]) -> None:
        """Store a value (redacted payloads only)."""

    @abc.abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key; return True if it existed."""


class SQLiteStateAdapterSkeleton(StateAdapter):
    """Interface skeleton. Does NOT open a real database in Phase 3."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path
        self._opened = False

    @property
    def opened(self) -> bool:
        return self._opened

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("SQLite state adapter is a Phase 3 skeleton; not implemented")

    def put(self, key: str, value: Dict[str, Any]) -> None:
        raise NotImplementedError("SQLite state adapter is a Phase 3 skeleton; not implemented")

    def delete(self, key: str) -> bool:
        raise NotImplementedError("SQLite state adapter is a Phase 3 skeleton; not implemented")


class NoopStateAdapter(StateAdapter):
    """In-memory fake for tests/demo; never persists to disk."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = dict(value)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None
