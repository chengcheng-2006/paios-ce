"""Fresh-copy handling for the fixed Phase 3 repository-maintenance fixture."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from typing import Iterable


class FixtureError(RuntimeError):
    """The trusted fixture source or a requested fresh copy is unsafe."""


def maintenance_fixture_source() -> Path:
    """Return the checked-out fixture source without searching user directories."""

    source = Path(__file__).resolve().parent / "fixtures" / "aic2026_repo_maintenance"
    if not source.is_dir() or source.is_symlink():
        raise FixtureError("Phase 3 fixture source is unavailable")
    return source


def tree_digest(root: Path, *, exclude: Iterable[str] = ()) -> str:
    """Hash regular files and relative names deterministically; reject symlinks."""

    excluded = set(exclude)
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(part in excluded for part in relative.split("/")):
            continue
        if path.is_symlink():
            raise FixtureError("fixture tree contains a symlink")
        if path.is_file():
            digest.update(relative.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(path.read_bytes())
            digest.update(b"\x00")
    return digest.hexdigest()


@dataclass(frozen=True)
class FixtureWorkspace:
    root: Path
    baseline_digest: str

    @classmethod
    def create(cls, destination: str | Path, *, source: Path | None = None) -> "FixtureWorkspace":
        source_root = source or maintenance_fixture_source()
        if not source_root.is_dir() or source_root.is_symlink():
            raise FixtureError("fixture source must be an existing non-symlink directory")
        target = Path(destination)
        if target.exists():
            raise FixtureError("fresh fixture destination already exists")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copytree(source_root, target, symlinks=False)
        for path in target.rglob("*"):
            if path.is_symlink():
                raise FixtureError("copied fixture contains a symlink")
        return cls(root=target.resolve(strict=True), baseline_digest=tree_digest(target))

    @classmethod
    def open_existing(cls, destination: str | Path, *, source: Path | None = None) -> "FixtureWorkspace":
        """Reopen only the exact trusted fixture after a bounded baseline test."""

        source_root = source or maintenance_fixture_source()
        target = Path(destination)
        if not source_root.is_dir() or source_root.is_symlink() or not target.is_dir() or target.is_symlink():
            raise FixtureError("existing fixture must be a non-symlink directory")
        source_digest = tree_digest(source_root)
        current_digest = tree_digest(target, exclude={"__pycache__", ".pytest_cache"})
        if current_digest != source_digest:
            raise FixtureError("existing fixture does not match the trusted fresh baseline")
        return cls(root=target.resolve(strict=True), baseline_digest=source_digest)
