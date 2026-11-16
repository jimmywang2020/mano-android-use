#!/usr/bin/env bash
# Start MCP after resolving a live ADB serial (phone wireless / USB / MuMu).
# Use as the MCP "command" in Cursor/Codex — do NOT pin a stale MANO_DEVICE_SERIAL
# in MCP env unless you intend to force that device (stale values are ignored).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer project venv / uv-managed binary when present.
if [[ -x "$ROOT/.venv/bin/mau-mcp" ]]; then
  MAU_MCP="$ROOT/.venv/bin/mau-mcp"
elif command -v mau-mcp >/dev/null 2>&1; then
  MAU_MCP="$(command -v mau-mcp)"
else
  echo "mau-mcp not found; run: uv sync --extra dev" >&2
  exit 1
fi

# Resolve serial every MCP start: keep env only if still "device", else re-pick.
# shellcheck disable=SC1091
eval "$(bash "$ROOT/scripts/resolve-adb-serial.sh")"

export MAU_RUNS_DIR="${MAU_RUNS_DIR:-$ROOT/runs}"
exec "$MAU_MCP" "$@"
