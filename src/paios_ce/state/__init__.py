"""State adapter interface (OPTIONAL — interface only).

The SQLite state adapter is declared as an interface stub. the release candidate does NOT
connect to any production database. A NoopStateAdapter is provided for tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .adapter import NoopStateAdapter, StateAdapter, SQLiteStateAdapterSkeleton

__all__ = ["NoopStateAdapter", "SQLiteStateAdapterSkeleton", "StateAdapter"]
