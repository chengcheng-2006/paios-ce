"""Thin adapters binding the Team layer to Astron's existing authority core.

Nothing in this package reimplements permission, journal, runtime, or verifier
logic.  Each adapter re-parameterizes an existing public ``paios_ce`` class so
that a Team role is expressed as a *narrowing* of the same authority the Single
harness already uses.  Astron keeps exactly one authority source.

SPDX-License-Identifier: Apache-2.0
"""

from .tool_authority import (
    ROLE_PRINCIPALS,
    ROLE_TOOL_PROFILES,
    RoleToolProfile,
    RoleScopedToolRuntime,
    UnknownRoleError,
)

__all__ = [
    "ROLE_PRINCIPALS",
    "ROLE_TOOL_PROFILES",
    "RoleScopedToolRuntime",
    "RoleToolProfile",
    "UnknownRoleError",
]
