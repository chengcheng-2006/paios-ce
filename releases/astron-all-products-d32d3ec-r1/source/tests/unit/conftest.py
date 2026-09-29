"""Phase 9A Local ASR fixtures (re-exported from the root conftest).

The shared helpers (write_small_wav, FakeModel, FakeSegment, FakeInfo,
make_fake_model_factory, fake_model fixture) live in ``tests/conftest.py`` so
they are importable from every test directory. This module keeps backward
compatibility for ``from .conftest import ...`` imports inside tests/unit.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import (  # noqa: E402,F401
    FakeInfo,
    FakeModel,
    FakeSegment,
    make_fake_model_factory,
    write_small_wav,
)
