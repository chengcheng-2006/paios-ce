"""paios-ce command line interface.

Subcommands: demo, health, validate-config, run-task <file>.
Defaults to the Mock Provider; never reads real secrets; never connects to any
network. Output is structured JSON. Exit codes are stable.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .main import main

__all__ = ["main"]
