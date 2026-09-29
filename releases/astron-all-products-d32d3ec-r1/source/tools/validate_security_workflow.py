#!/usr/bin/env python3
"""Deterministic security workflow invariant validator.

Guarantees that the GitHub Actions Security workflow keeps its frozen gates:
- pip-audit process exit code is captured and ENFORCED (non-zero => FAIL)
- invalid JSON => FAIL, vulnerabilities > 0 => FAIL
- the audit evidence artifact (pip-audit.json, pip-freeze.txt, pip-audit-summary.txt)
  is uploaded
- dependency-check does not use continue-on-error

Removal of any enforced gate fails this check, which runs inside the Security
workflow itself and in local validation.
"""
import os
import sys

WF = os.path.join(os.path.dirname(__file__), '..', '.github', 'workflows', 'security.yml')
WF = os.path.normpath(WF)

REQUIRED = [
    ("audit exit captured", "audit_exit=$?"),
    ("audit exit exported", "export AUDIT_EXIT=$audit_exit"),
    ("audit exit enforced", "if audit_exit != 0:"),
    ("audit exit error msg", "CHECK_ERROR: pip-audit exited with"),
    ("invalid json fails", "CHECK_ERROR: "),
    ("vulns gate", "VULNERABILITIES_FOUND"),
    ("artifact upload action", "actions/upload-artifact@v4"),
    ("artifact name", "security-audit-python-3.11"),
    ("audit json member", "pip-audit.json"),
    ("inventory member", "pip-freeze.txt"),
    ("summary member", "pip-audit-summary.txt"),
]

FORBIDDEN = [
    ("continue-on-error not allowed", "continue-on-error: true"),
]


def main() -> int:
    with open(WF, 'r', encoding='utf-8') as f:
        content = f.read()
    failures = []
    for label, needle in REQUIRED:
        if needle not in content:
            failures.append(f'MISSING: {label} ({needle!r})')
    for label, needle in FORBIDDEN:
        if needle in content:
            failures.append(f'FORBIDDEN: {label} ({needle!r})')
    if failures:
        print('SECURITY_WORKFLOW_INVARIANTS_FAIL:')
        for f in failures:
            print('  - ' + f)
        return 1
    print(f'SECURITY_WORKFLOW_INVARIANTS_PASS ({len(REQUIRED)} required, {len(FORBIDDEN)} forbidden)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
