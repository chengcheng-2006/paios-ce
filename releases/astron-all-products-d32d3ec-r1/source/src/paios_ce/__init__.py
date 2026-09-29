"""Legacy internal compatibility namespace for Astron.

Astron adopts the public PAIOS CE baseline as its competition source. The
``paios_ce`` import namespace remains temporarily for compatibility; it is not
evidence that historical PAIOS CE was called Astron. This package contains no
real secrets, Owner PII, or production configuration. See README.md and
docs/aic2026/CONTRIBUTION_BOUNDARY.md.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

__version__ = "0.1.0rc2"
__all__ = ["__version__"]
