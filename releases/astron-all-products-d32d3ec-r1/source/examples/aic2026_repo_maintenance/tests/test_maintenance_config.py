from maintenance_config import DEFAULT_TIMEOUT_SECONDS


def test_default_timeout_is_safe_for_interactive_maintenance() -> None:
    assert DEFAULT_TIMEOUT_SECONDS == 30
