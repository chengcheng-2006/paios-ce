"""Platform-semantic tests for durable private-file access control."""

from __future__ import annotations

from pathlib import Path

import pytest

from paios_ce.state.private_files import (
    PrivateFileSecurityError,
    PrivateFileSecurityStatus,
    _sddl_is_owner_private,
    ensure_private_file,
    verify_private_file,
)


class _FakeWindowsAccessControl:
    def __init__(self, *, fail_at: str | None = None) -> None:
        self.fail_at = fail_at
        self.calls: list[tuple[str, Path]] = []

    def _record(self, operation: str, path: Path) -> None:
        self.calls.append((operation, path))
        if self.fail_at == operation:
            raise PrivateFileSecurityError(f"{operation} failed")

    def verify_directory(self, path: Path) -> None:
        self._record("verify_directory", path)

    def restrict_file(self, path: Path) -> None:
        self._record("restrict_file", path)

    def verify_file(self, path: Path, *, require_protected: bool = True) -> None:
        assert require_protected is True
        self._record("verify_file", path)


def test_windows_new_file_requires_parent_restriction_and_verified_dacl(tmp_path: Path) -> None:
    backend = _FakeWindowsAccessControl()
    path = tmp_path / "state.sqlite"

    status = ensure_private_file(
        path,
        platform_name="nt",
        windows_backend=backend,
    )

    assert status is PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE
    assert backend.calls == [
        ("verify_directory", tmp_path),
        ("restrict_file", path),
        ("verify_file", path),
    ]


def test_windows_existing_file_is_verified_without_silent_acl_repair(tmp_path: Path) -> None:
    backend = _FakeWindowsAccessControl()
    path = tmp_path / "state.sqlite"
    path.write_bytes(b"existing")

    status = ensure_private_file(
        path,
        platform_name="nt",
        windows_backend=backend,
    )

    assert status is PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE
    assert backend.calls == [
        ("verify_directory", tmp_path),
        ("verify_file", path),
    ]


@pytest.mark.parametrize("operation", ["verify_directory", "restrict_file", "verify_file"])
def test_windows_private_file_contract_fails_closed(operation: str, tmp_path: Path) -> None:
    backend = _FakeWindowsAccessControl(fail_at=operation)

    with pytest.raises(PrivateFileSecurityError):
        ensure_private_file(
            tmp_path / "state.sqlite",
            platform_name="nt",
            windows_backend=backend,
        )


def test_windows_sddl_rejects_broad_or_unprotected_access() -> None:
    user = "S-1-5-21-100-200-300-1001"
    protected = f"O:{user}D:P(A;;FA;;;SY)(A;;FA;;;{user})"
    broad = protected + "(A;;FR;;;BU)"
    unprotected = f"O:{user}D:AI(A;;FA;;;SY)(A;;FA;;;{user})"

    assert _sddl_is_owner_private(
        protected,
        current_user_sid=user,
        require_protected=True,
    )
    assert not _sddl_is_owner_private(
        broad,
        current_user_sid=user,
        require_protected=True,
    )
    assert not _sddl_is_owner_private(
        unprotected,
        current_user_sid=user,
        require_protected=True,
    )
    assert _sddl_is_owner_private(
        unprotected,
        current_user_sid=user,
        require_protected=False,
    )


def test_posix_private_file_contract_rejects_group_access(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite"
    path.write_bytes(b"state")
    path.chmod(0o640)

    with pytest.raises(PrivateFileSecurityError, match="group or world"):
        verify_private_file(path, platform_name="posix")
