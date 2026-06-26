#!/usr/bin/env bash
set -euo pipefail

# Run the A2A Olympics demo agents.
# Assumes agent files live under notebooks/a2a_olympics/:
#   generalist_agent.py, math_agent.py, schema_agent.py, story_agent.py
#
# Usage:
#   scripts/a2a/run_olympics.sh
#   RELOAD=1 scripts/a2a/run_olympics.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RELOAD_FLAG="${RELOAD:-0}"
RELOAD_ARGS=""
if [[ "$RELOAD_FLAG" == "1" ]]; then
  RELOAD_ARGS="--reload"
fi

HOST="127.0.0.1"
GEN_PORT="${GEN_PORT:-8100}"
MATH_PORT="${MATH_PORT:-8101}"
SCHEMA_PORT="${SCHEMA_PORT:-8102}"
STORY_PORT="${STORY_PORT:-8103}"

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "Starting GENERALIST on http://${HOST}:${GEN_PORT}"
python -m uvicorn --app-dir notebooks/a2a_olympics generalist_agent:app --host "$HOST" --port "$GEN_PORT" $RELOAD_ARGS &
pids+=($!)

echo "Starting MATH      on http://${HOST}:${MATH_PORT}"
python -m uvicorn --app-dir notebooks/a2a_olympics math_agent:app --host "$HOST" --port "$MATH_PORT" $RELOAD_ARGS &
pids+=($!)

echo "Starting SCHEMA    on http://${HOST}:${SCHEMA_PORT}"
python -m uvicorn --app-dir notebooks/a2a_olympics schema_agent:app --host "$HOST" --port "$SCHEMA_PORT" $RELOAD_ARGS &
pids+=($!)

echo "Starting STORY     on http://${HOST}:${STORY_PORT}"
python -m uvicorn --app-dir notebooks/a2a_olympics story_agent:app --host "$HOST" --port "$STORY_PORT" $RELOAD_ARGS &
pids+=($!)

echo ""
echo "Olympics agents running. Ctrl+C to stop."
echo ""

wait
