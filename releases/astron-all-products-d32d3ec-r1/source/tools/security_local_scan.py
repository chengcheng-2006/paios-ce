#!/usr/bin/env python3
"""Local equivalent of .github/workflows/security.yml — offline secret/forbidden scan.

Usage: python tools/security_local_scan.py [root]
Exit 1 on any finding. No network, no upload.
"""
import os
import re
import sys

PATTERNS = {
    "OpenAI_SK": re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    "GitHub_PAT": re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    "GitHub_FineGrained": re.compile(r"github_pat_[a-zA-Z0-9]+"),
    "Google_API": re.compile(r"AIza[a-zA-Z0-9_-]{35,}"),
    "AWS": re.compile(r"AKIA[a-zA-Z0-9]{16}"),
    "Slack": re.compile(r"xoxb-[a-zA-Z0-9-]+"),
    "PrivateKey": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

FORBIDDEN_FILES = {
    ".env", "credentials.json", "secrets.json", "private.key", "id_rsa",
    "policy.py.orig", ".pypirc", ".netrc", ".npmrc",
}
FORBIDDEN_SUFFIXES = (".orig", ".pem", ".p12", ".pfx", ".key")
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "build", "dist", ".pytest_cache"}


def main(argv):
    root = argv[1] if len(argv) > 1 else "."
    findings = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            if fn in FORBIDDEN_FILES or fn.endswith(FORBIDDEN_SUFFIXES):
                findings.append(f"FORBIDDEN_FILE: {rel}")
            # text scan
            try:
                with open(path, "r", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for name, pat in PATTERNS.items():
                            if pat.search(line):
                                findings.append(f"SECRET_PATTERN[{name}]: {rel}:{lineno}")
            except OSError:
                continue

    if findings:
        print("SECURITY_LOCAL_SCAN_FINDINGS:")
        for f in findings[:50]:
            print(f"  {f}")
        print(f"TOTAL: {len(findings)}")
        return 1
    print("SECURITY_LOCAL_SCAN_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
