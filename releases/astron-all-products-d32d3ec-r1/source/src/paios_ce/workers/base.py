"""Worker contract (worker permission model).

A worker executes a single ActionRequest under a bounded scope. Workers are
deny-by-default: they hold only the capabilities explicitly granted for the
task. The current release candidate implements MockWorker only.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import abc

from ..protocols import ActionRequest, ActionResult


class Worker(abc.ABC):
    """Executes an ActionRequest under scope/permission control."""

    worker_type: str = "abstract"

    @abc.abstractmethod
    def execute(self, request: ActionRequest) -> ActionResult:
        """Execute the action and return a redacted ActionResult."""
