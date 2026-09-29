"""Cross-platform private-file security contract for durable local authority.

POSIX implementations enforce owner-only mode bits. Windows implementations
set and query a protected DACL; POSIX mode bits are never treated as an NTFS
access-control proof.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from enum import Enum
import os
from pathlib import Path
import re
import stat
from typing import Optional, Protocol


class PrivateFileSecurityStatus(str, Enum):
    VERIFIED_OWNER_PRIVATE = "VERIFIED_OWNER_PRIVATE"


class PrivateFileSecurityError(RuntimeError):
    """A platform privacy guarantee could not be established or verified."""


class _WindowsAccessControl(Protocol):
    def verify_directory(self, path: Path) -> None: ...

    def restrict_file(self, path: Path) -> None: ...

    def verify_file(self, path: Path, *, require_protected: bool = True) -> None: ...


_WINDOWS_BACKEND: Optional[_WindowsAccessControl] = None


def _inspect_regular_file(path: Path) -> os.stat_result:
    if path.is_symlink():
        raise PrivateFileSecurityError("private file path must not be a symlink")
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise PrivateFileSecurityError("private file cannot be inspected") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise PrivateFileSecurityError("private file path is not a regular file")
    return file_stat


def _verify_posix_file(path: Path) -> None:
    permissions = stat.S_IMODE(_inspect_regular_file(path).st_mode)
    if permissions & 0o077:
        raise PrivateFileSecurityError("private file has group or world access")


def _windows_backend() -> _WindowsAccessControl:
    global _WINDOWS_BACKEND
    if _WINDOWS_BACKEND is None:
        _WINDOWS_BACKEND = _NativeWindowsAccessControl()
    return _WINDOWS_BACKEND


def ensure_private_file(
    path: Path,
    *,
    platform_name: Optional[str] = None,
    windows_backend: Optional[_WindowsAccessControl] = None,
) -> PrivateFileSecurityStatus:
    """Create a new private file or verify an existing one without repair."""
    path = Path(path)
    if path.is_symlink():
        raise PrivateFileSecurityError("private file path must not be a symlink")
    parent = path.parent
    if not parent.is_dir():
        raise PrivateFileSecurityError("private file parent directory does not exist")
    platform = os.name if platform_name is None else platform_name
    backend = windows_backend
    if platform == "nt":
        backend = backend or _windows_backend()
        # SQLite journals and sidecars inherit from the containing directory.
        # A broad parent therefore cannot support sensitive durable authority.
        backend.verify_directory(parent)
    created = False
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    except OSError as exc:
        raise PrivateFileSecurityError("private file cannot be created") from exc
    else:
        os.close(descriptor)
        created = True
    _inspect_regular_file(path)
    if platform == "nt":
        assert backend is not None
        if created:
            backend.restrict_file(path)
        backend.verify_file(path, require_protected=True)
    else:
        _verify_posix_file(path)
    return PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE


def harden_private_file(
    path: Path,
    *,
    platform_name: Optional[str] = None,
    windows_backend: Optional[_WindowsAccessControl] = None,
) -> PrivateFileSecurityStatus:
    """Restrict a file known to have been created by the current operation."""
    path = Path(path)
    _inspect_regular_file(path)
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        backend = windows_backend or _windows_backend()
        backend.restrict_file(path)
        backend.verify_file(path, require_protected=True)
    else:
        try:
            path.chmod(0o600)
        except OSError as exc:
            raise PrivateFileSecurityError("private file mode cannot be restricted") from exc
        _verify_posix_file(path)
    return PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE


def verify_private_file(
    path: Path,
    *,
    platform_name: Optional[str] = None,
    windows_backend: Optional[_WindowsAccessControl] = None,
    require_protected_windows_dacl: bool = True,
) -> PrivateFileSecurityStatus:
    """Verify the platform privacy invariant without changing the file."""
    path = Path(path)
    _inspect_regular_file(path)
    platform = os.name if platform_name is None else platform_name
    if platform == "nt":
        (windows_backend or _windows_backend()).verify_file(
            path,
            require_protected=require_protected_windows_dacl,
        )
    else:
        _verify_posix_file(path)
    return PrivateFileSecurityStatus.VERIFIED_OWNER_PRIVATE


def _sddl_is_owner_private(
    sddl: str,
    *,
    current_user_sid: str,
    require_protected: bool,
) -> bool:
    """Conservatively validate owner and allow ACEs from an SDDL descriptor."""
    owner_match = re.search(r"O:(.*?)(?=(?:G|D|S):|$)", sddl)
    dacl_marker = sddl.find("D:")
    if owner_match is None or dacl_marker < 0:
        return False
    owner = owner_match.group(1)
    trusted = {
        current_user_sid,
        "SY",
        "S-1-5-18",
        "BA",
        "S-1-5-32-544",
    }
    if owner not in trusted:
        return False
    dacl = sddl[dacl_marker + 2 :]
    sacl_marker = dacl.find("S:")
    if sacl_marker >= 0:
        dacl = dacl[:sacl_marker]
    dacl_flags = dacl.split("(", 1)[0]
    if require_protected and "P" not in dacl_flags:
        return False
    current_user_allowed = False
    aces = re.findall(r"\(([^()]*)\)", dacl)
    if not aces:
        return False
    for encoded in aces:
        fields = encoded.split(";")
        if len(fields) != 6:
            return False
        ace_type, ace_flags, _rights, _object, _inherit_object, trustee = fields
        if ace_type == "A":
            if trustee in trusted:
                if trustee == current_user_sid:
                    current_user_allowed = True
                continue
            if trustee in {"CO", "S-1-3-0", "OW", "S-1-3-4"} and "IO" in ace_flags:
                continue
            return False
        if ace_type == "D":
            continue
        # Object/callback/resource allow ACEs are rejected rather than parsed
        # incompletely. Astron's own protected file DACL never needs them.
        return False
    return current_user_allowed


class _NativeWindowsAccessControl:
    """Small stdlib-only Windows DACL adapter used only when os.name == 'nt'."""

    _OWNER_SECURITY_INFORMATION = 0x00000001
    _DACL_SECURITY_INFORMATION = 0x00000004
    _PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
    _SE_FILE_OBJECT = 1
    _TOKEN_QUERY = 0x0008
    _TOKEN_USER = 1
    _SDDL_REVISION_1 = 1

    def __init__(self) -> None:
        self._current_sid = self._current_user_sid()

    @staticmethod
    def _libraries():
        try:
            import ctypes
            from ctypes import wintypes

            return ctypes, wintypes, ctypes.WinDLL("advapi32", use_last_error=True), ctypes.WinDLL(
                "kernel32", use_last_error=True
            )
        except (AttributeError, OSError) as exc:
            raise PrivateFileSecurityError("Windows access-control API is unavailable") from exc

    @classmethod
    def _current_user_sid(cls) -> str:
        ctypes, wintypes, advapi32, kernel32 = cls._libraries()
        class _SidAndAttributes(ctypes.Structure):
            _fields_ = [("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD)]

        class _TokenUser(ctypes.Structure):
            _fields_ = [("user", _SidAndAttributes)]

        token = wintypes.HANDLE()
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), cls._TOKEN_QUERY, ctypes.byref(token)
        ):
            raise PrivateFileSecurityError("Windows process token cannot be queried")
        try:
            required = wintypes.DWORD()
            advapi32.GetTokenInformation(
                token, cls._TOKEN_USER, None, 0, ctypes.byref(required)
            )
            if required.value == 0:
                raise PrivateFileSecurityError("Windows user SID size cannot be queried")
            buffer = ctypes.create_string_buffer(required.value)
            if not advapi32.GetTokenInformation(
                token,
                cls._TOKEN_USER,
                ctypes.cast(buffer, ctypes.c_void_p),
                required,
                ctypes.byref(required),
            ):
                raise PrivateFileSecurityError("Windows user SID cannot be queried")
            sid_pointer = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents.user.sid
            sid_text = wintypes.LPWSTR()
            advapi32.ConvertSidToStringSidW.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.LPWSTR),
            ]
            advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
            if not advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid_text)):
                raise PrivateFileSecurityError("Windows user SID cannot be converted")
            try:
                return sid_text.value
            finally:
                kernel32.LocalFree(sid_text)
        finally:
            kernel32.CloseHandle(token)

    @classmethod
    def _read_sddl(cls, path: Path) -> str:
        ctypes, wintypes, advapi32, kernel32 = cls._libraries()
        owner = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        advapi32.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        result = advapi32.GetNamedSecurityInfoW(
            str(path),
            cls._SE_FILE_OBJECT,
            cls._OWNER_SECURITY_INFORMATION | cls._DACL_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if result != 0:
            raise PrivateFileSecurityError("Windows DACL cannot be queried")
        try:
            rendered = wintypes.LPWSTR()
            rendered_length = wintypes.ULONG()
            advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(wintypes.ULONG),
            ]
            advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
            if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor,
                cls._SDDL_REVISION_1,
                cls._OWNER_SECURITY_INFORMATION | cls._DACL_SECURITY_INFORMATION,
                ctypes.byref(rendered),
                ctypes.byref(rendered_length),
            ):
                raise PrivateFileSecurityError("Windows DACL cannot be rendered")
            try:
                return rendered.value
            finally:
                kernel32.LocalFree(rendered)
        finally:
            kernel32.LocalFree(descriptor)

    def verify_directory(self, path: Path) -> None:
        if not _sddl_is_owner_private(
            self._read_sddl(path),
            current_user_sid=self._current_sid,
            require_protected=False,
        ):
            raise PrivateFileSecurityError(
                "Windows parent directory access control is not owner-private"
            )

    def restrict_file(self, path: Path) -> None:
        ctypes, wintypes, advapi32, kernel32 = self._libraries()
        sddl = f"D:P(A;;FA;;;SY)(A;;FA;;;{self._current_sid})"
        descriptor = ctypes.c_void_p()
        descriptor_size = wintypes.ULONG()
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.ULONG),
        ]
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
        advapi32.SetFileSecurityW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        advapi32.SetFileSecurityW.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl,
            self._SDDL_REVISION_1,
            ctypes.byref(descriptor),
            ctypes.byref(descriptor_size),
        ):
            raise PrivateFileSecurityError("Windows private DACL cannot be constructed")
        try:
            if not advapi32.SetFileSecurityW(
                str(path),
                self._DACL_SECURITY_INFORMATION
                | self._PROTECTED_DACL_SECURITY_INFORMATION,
                descriptor,
            ):
                raise PrivateFileSecurityError("Windows private DACL cannot be applied")
        finally:
            kernel32.LocalFree(descriptor)

    def verify_file(self, path: Path, *, require_protected: bool = True) -> None:
        if not _sddl_is_owner_private(
            self._read_sddl(path),
            current_user_sid=self._current_sid,
            require_protected=require_protected,
        ):
            raise PrivateFileSecurityError("Windows file DACL is not owner-private")
