"""Astron Team runtime.

C1 supplies the offline orchestration skeleton: typed mailbox, append-only state
projection, fixed sequential scheduler, and the Supervisor/Executor/Auditor role
contracts.  The package is intentionally outside ``src/`` and calls no live
provider.

C2 adds the authority binding, in sibling modules:

    team/authority.py   role -> capability profiles over the existing engine
    team/lifecycle.py   the single governed path for one Team action
    team/journal.py     append-only projection, provable against the journal
    team/verifier.py    sole gate in front of TASK_COMPLETED
    team/adapters/      thin re-parameterization of existing src/ classes

Those modules are imported explicitly rather than re-exported here, so the C1
skeleton keeps working without importing ``paios_ce``.
"""

from .mailbox import Mailbox, MailboxError, MessageType, TeamMessage, TeamRole
from .mock_provider import MaintenanceTeamProvider, MockLLMProvider, ProviderCall
from .scheduler import TeamRunResult, TeamScheduler
from .state import TeamEvent, TeamPhase, TeamState

__all__ = [
    "Mailbox",
    "MailboxError",
    "MaintenanceTeamProvider",
    "MessageType",
    "MockLLMProvider",
    "ProviderCall",
    "TeamEvent",
    "TeamMessage",
    "TeamPhase",
    "TeamRole",
    "TeamRunResult",
    "TeamScheduler",
    "TeamState",
]
