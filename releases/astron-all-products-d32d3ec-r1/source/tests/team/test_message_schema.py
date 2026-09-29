from __future__ import annotations

from datetime import datetime, timezone

import pytest

from team.mailbox import MailboxError, MessageType, TeamMessage, TeamRole


def test_message_schema_serializes_and_round_trips() -> None:
    message = TeamMessage(
        task_id="task-1",
        run_id="run-1",
        sender=TeamRole.HARNESS,
        receiver=TeamRole.SUPERVISOR,
        message_type=MessageType.TASK,
        state_version=0,
        parent_message_id=None,
        timestamp=datetime(2026, 9, 11, tzinfo=timezone.utc),
        payload={"objective": "offline"},
        message_id="tm-1",
    )

    restored = TeamMessage.from_dict(message.to_dict())

    assert restored == message
    assert restored.to_dict()["message_type"] == "TASK"
    assert restored.to_dict()["payload"] == {"objective": "offline"}


def test_message_schema_rejects_invalid_state_and_payload() -> None:
    with pytest.raises(MailboxError):
        TeamMessage(
            task_id="task-1",
            run_id="run-1",
            sender="HARNESS",
            receiver="SUPERVISOR",
            message_type="TASK",
            state_version=-1,
        )
    with pytest.raises(MailboxError):
        TeamMessage(
            task_id="task-1",
            run_id="run-1",
            sender="HARNESS",
            receiver="SUPERVISOR",
            message_type="TASK",
            state_version=0,
            payload={"not_json": object()},
        )
