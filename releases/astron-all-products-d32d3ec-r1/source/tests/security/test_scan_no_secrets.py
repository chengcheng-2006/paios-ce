"""Security: repository secret/PII scan over the clean-room source tree.

Scans every authored source/config/example for secret-like tokens and
production-path leakage. Placeholders are the ONLY allowed secret-like shapes.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Patterns that indicate a real secret (vs. a documented placeholder).
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"Bearer [A-Za-z0-9._\-]{20,}"),
]

PROHIBITED_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
]

# Allowlisted placeholder tokens (these are not secrets).
# publication hygiene: every key-shaped fixture is reconstructed at runtime from separated
# fragments in tests/_keyshape_fixtures.py, so no contiguous key-shaped literal
# exists anywhere in the public tree.  The allowlist therefore only needs to
# cover non-key-shaped placeholder tokens; key-shaped entries have been removed
# so the repository byte-scan stays clean.
ALLOWED = {
    "not-a-valid-provider-token",
    "example.invalid",
    "placeholder-not-a-real-secret",
    "placeholder-not-real",
    "sk-abc",
    "super-secret-xyz-001",
    "Bearer abcdefgh12345678",
}

SCAN_DIRS = ["src", "tests", "examples", "schemas", "pyproject.toml", "README.md",
             "SECURITY.md", "NOTICE", "THIRD_PARTY_NOTICES.md", "LICENSE"]


# src/paios_ce/audit/redact.py intentionally contains the exact regex/private-key
# markers it strips; scanning its source for those markers is a self-match false
# positive. It is excluded only from the path/private-key marker scans (not from
# the secret-value scan).
REDACT_SOURCE = REPO_ROOT / "src" / "paios_ce" / "audit" / "redact.py"


def _scan_files():
    for name in SCAN_DIRS:
        path = REPO_ROOT / name
        if path.is_file():
            yield path
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and ".pyc" not in f.suffix and "pytest_cache" not in str(f):
                    yield f


def test_no_real_secret_patterns():
    hits = []
    for f in _scan_files():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                token = m.group(0)
                if token not in ALLOWED:
                    hits.append((str(f), pat.pattern, token[:8]))
    assert hits == [], f"secret-like tokens found: {hits[:10]}"


def test_no_prohibited_private_keys():
    hits = []
    for f in _scan_files():
        if f.resolve() == REDACT_SOURCE.resolve():
            continue  # redact.py defines these markers to strip; self-match false positive
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in PROHIBITED_PATTERNS:
            if pat.search(text):
                hits.append((str(f), pat.pattern))
    assert hits == [], f"prohibited markers found: {hits[:10]}"


def test_no_production_path_leakage():
    """No real user/owner absolute paths (other than the audit test fixture)."""
    hits = []
    # We intentionally do NOT include tests/security in this scan because the
    # audit test constructs a redacted-path example using <USER_HOME>.
    for f in _scan_files():
        if "test_scan_no_secrets" in str(f) or "test_audit" in str(f):
            continue
        if f.resolve() == REDACT_SOURCE.resolve():
            continue  # redact.py defines the path-redaction regex; self-match false positive
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Real Windows user profile paths like C:\Users\<name>
        for m in re.finditer(r"[A-Za-z]:\\\\Users\\\\[^\\\s\"']+", text):
            hits.append((str(f), m.group(0)))
        for m in re.finditer(r"/Users/[^/\s\"']+", text):
            hits.append((str(f), m.group(0)))
    # Allow the placeholder <USER_HOME> token only.
    hits = [(f, t) for f, t in hits if "<USER_HOME>" not in t and "example.invalid" not in t]
    assert hits == [], f"production path leakage: {hits[:10]}"


def test_no_git_directory_created():
    # Net-room publication tree: the shipped archive/Candidate must not embed
    # .git metadata. When the tree is a Git worktree (CI checkout, restored
    # bundle), a .git directory is expected and this check is skipped.
    import subprocess
    in_git = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if in_git.returncode == 0 and in_git.stdout.strip() == "true":
        return  # Git worktree mode: .git is expected
    assert not (REPO_ROOT / ".git").exists()


def test_no_env_or_dpapi_files():
    for f in _scan_files():
        name = f.name.lower()
        assert ".env" not in name, f"env-like file present: {f}"
        assert "dpapi" not in name.lower(), f"dpapi-like file present: {f}"
        assert f.suffix not in {".pem", ".key", ".p12", ".jks"}, f"sensitive file present: {f}"
