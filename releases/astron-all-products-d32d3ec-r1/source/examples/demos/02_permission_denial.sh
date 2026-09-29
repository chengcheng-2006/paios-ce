#!/usr/bin/env bash
# Astron demo 2 - the deny path. Every action below is proposed with the same
# JSON shape; only the runtime decides. Denied and blocked actions never reach an
# executor, so the protected goal is unchanged by the attempt.
set -uo pipefail

command -v astron >/dev/null 2>&1 || {
  echo "astron CLI not found. Install the package first: pip install -e \".[dev]\"" >&2
  exit 1
}

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/astron-demo2-XXXXXX")"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
# The config models emit a known pydantic UserWarning about the schema-required
# field name "schema"; pyproject.toml silences the same warning for pytest.
export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore:Field name \"schema\" in :UserWarning}"
echo "[demo2] artifacts directory: $WORKDIR"
echo "[demo2] fixtures used: $REPO/examples"
echo

cat > "$WORKDIR/shell_action.json" <<'JSON'
{
  "manifest_version": "0.1.0",
  "action_id": "act_demo2_shell_001",
  "worker_type": "tool",
  "operation": "system.shell.exec",
  "parameters": {"trace_id": "trace_demo2"},
  "required_permissions": ["TEXT_CHAT", "TOOL_CALLING"],
  "filesystem_scope": {"mode": "none", "paths_class": []},
  "network_scope": {"mode": "none", "endpoints_class": []},
  "timeout": 30,
  "idempotency_key": "idem_demo2_shell_001",
  "rollback_supported": false,
  "approval_required": false
}
JSON

cat > "$WORKDIR/outside_scope_action.json" <<'JSON'
{
  "manifest_version": "0.1.0",
  "action_id": "act_demo2_scope_001",
  "worker_type": "tool",
  "operation": "workspace.read_text",
  "parameters": {"trace_id": "trace_demo2"},
  "required_permissions": ["TEXT_CHAT"],
  "filesystem_scope": {"mode": "read", "paths_class": ["owner_private_home"]},
  "network_scope": {"mode": "none", "endpoints_class": []},
  "timeout": 30,
  "idempotency_key": "idem_demo2_scope_001",
  "rollback_supported": false,
  "approval_required": false
}
JSON

cat > "$WORKDIR/allowed_action.json" <<'JSON'
{
  "manifest_version": "0.1.0",
  "action_id": "act_demo2_allow_001",
  "worker_type": "tool",
  "operation": "workspace.read_text",
  "parameters": {"trace_id": "trace_demo2"},
  "required_permissions": ["TEXT_CHAT"],
  "filesystem_scope": {"mode": "read", "paths_class": []},
  "network_scope": {"mode": "none", "endpoints_class": []},
  "timeout": 30,
  "idempotency_key": "idem_demo2_allow_001",
  "rollback_supported": false,
  "approval_required": false
}
JSON

run_case() {
  local label="$1" file="$2"
  echo "---------------------------------------------------------------"
  echo "[demo2] $label"
  echo "[demo2]   \$ astron run-task $file"
  astron run-task "$file" | grep -E '"decision"|"action_class"|"risk_level"|"error_code"|"execution_attempted"|"hard_blocked"|"reason"'
  echo "[demo2]   exit code: ${PIPESTATUS[0]}  (0 ok, 4 denied, 5 blocked)"
  echo
}

run_case "baseline: an in-scope read with a granted capability is ALLOWED" \
  "$WORKDIR/allowed_action.json"
run_case "unknown operation: never coerced into a known class, rejected first" \
  "$REPO/examples/unknown_action_fixture.json"
run_case "cloud egress requested by an unregistered action" \
  "$REPO/examples/unknown_egress_fixture.json"
run_case "arbitrary shell syntax: hard block, no executor is created" \
  "$WORKDIR/shell_action.json"
run_case "read outside the granted filesystem scope class" \
  "$WORKDIR/outside_scope_action.json"

echo "---------------------------------------------------------------"
echo "[demo2] what this shows : decisions come from the runtime, and every"
echo "                           rejection reports execution_attempted=false."
echo "[demo2] what it does NOT show: OS-level isolation. A blocked action is"
echo "                           never dispatched by Astron; Astron does not"
echo "                           contain a compromised operating system."
