"""Worker contract and MockWorker (worker permission model).

Workers in this release candidate only use MockWorker. No real shell, PowerShell, file deletion,
or network write is ever executed.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .base import Worker
from .mock import MockWorker

__all__ = ["MockWorker", "Worker"]
