"""State adapter skeleton / noop unit tests.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import pytest

from paios_ce.state import NoopStateAdapter, SQLiteStateAdapterSkeleton


def test_noop_adapter_roundtrip():
    a = NoopStateAdapter()
    a.put("k1", {"summary_class": "summary_produced"})
    assert a.get("k1")["summary_class"] == "summary_produced"
    assert a.delete("k1") is True
    assert a.get("k1") is None


def test_sqlite_skeleton_never_opens():
    a = SQLiteStateAdapterSkeleton(path="not-a-real-db.db")
    assert a.opened is False
    with pytest.raises(NotImplementedError):
        a.put("k", {})
    with pytest.raises(NotImplementedError):
        a.get("k")
