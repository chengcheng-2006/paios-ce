"""Fixed Team R1 role interfaces."""

from .auditor import AuditorRole
from .base import RoleInterface, RoleProtocolError
from .executor import ExecutorRole
from .supervisor import SupervisorRole

__all__ = [
    "AuditorRole",
    "ExecutorRole",
    "RoleInterface",
    "RoleProtocolError",
    "SupervisorRole",
]
