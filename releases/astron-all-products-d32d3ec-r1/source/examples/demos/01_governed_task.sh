#!/usr/bin/env bash
# Astron demo 1 - one governed task, end to end, with no model and no network.
# The proposals come from the offline Mock provider; every effect still goes
# through the permission engine, the durable SQLite journal and the verifier.
set -euo pipefail

command -v astron >/dev/null 2>&1 || {
  echo "astron CLI not found. Install the package first: pip install -e \".[dev]\"" >&2
  exit 1
}

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/astron-demo1-XXXXXX")"
# The config models emit a known pydantic UserWarning about the schema-required
# field name "schema"; pyproject.toml silences the same warning for pytest.
export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore:Field name \"schema\" in :UserWarning}"
echo "[demo1] artifacts directory: $WORKDIR"
echo

echo "[demo1] step 1 - certify the trusted fixture fails BEFORE any model runs"
echo "        (bounded pytest tool, no governance bypass)"
astron maintenance-baseline \
  --workspace "$WORKDIR/baseline" \
  --state-db "$WORKDIR/baseline.sqlite" \
  --task-id demo1-baseline
echo

echo "[demo1] step 2 - run the same fixture through the governed loop"
astron maintenance-demo --mode mock \
  --workspace "$WORKDIR/workspace" \
  --state-db "$WORKDIR/state.sqlite" \
  --task-id demo1-task
echo

echo "[demo1] produced files"
echo "  durable state      : $WORKDIR/state.sqlite"
echo "  agent source edit  : $WORKDIR/workspace/maintenance_config.py"
echo "  completion artifact: $WORKDIR/workspace/.astron-artifacts/change_summary.json"
echo
echo "[demo1] read the durable facts back (authorization, journal, checkpoint,"
echo "        verification) with:"
echo "        sqlite3 $WORKDIR/state.sqlite '.tables'"
echo "        sqlite3 $WORKDIR/state.sqlite 'select current_state,journal_sequence from action_journal'"
echo "        sqlite3 $WORKDIR/state.sqlite 'select reason_code from task_verifications'"
