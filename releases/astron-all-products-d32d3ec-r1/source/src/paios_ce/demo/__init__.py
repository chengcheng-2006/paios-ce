"""Demo workflow (mock provider demo mode).

Runs the full closed loop entirely locally: user input -> TaskEnvelope ->
Risk evaluation -> Mock Provider -> Mock Worker (optional) -> TaskResult ->
redacted audit. No API key, no network.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from .demo import run_demo

__all__ = ["run_demo"]
