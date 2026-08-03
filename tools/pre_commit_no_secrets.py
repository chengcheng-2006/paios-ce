#!/usr/bin/env python3
"""Local pre-commit hook: reject secret-shaped literals in staged files.

Usage: python tools/pre_commit_no_secrets.py <file...>
Exit 1 if any secret-shaped pattern is found. Offline, no network, no upload.
"""
import re
import sys

PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9]+"),
    re.compile(r"AIza[a-zA-Z0-9_-]{35,}"),
    re.compile(r"AKIA[a-zA-Z0-9]{16}"),
    re.compile(r"xoxb-[a-zA-Z0-9-]+"),
]

def main(argv):
    found = False
    for path in argv[1:]:
        try:
            with open(path, "r", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    for pat in PATTERNS:
                        if pat.search(line):
                            print(f"SECRET_PATTERN: {path}:{lineno}: {pat.pattern}")
                            found = True
        except OSError:
            pass
    return 1 if found else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
