#!/usr/bin/env bash
# Start MCP after auto-detecting MuMu ADB serial (no hardcoded port).
# Use this as the MCP "command" in Cursor/Codex when driving MuMu.
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

# If serial already set (USB device / CI), keep it; else probe MuMu.
if [[ -z "${MANO_DEVICE_SERIAL:-}" ]]; then
  # shellcheck disable=SC1091
  eval "$(bash "$ROOT/scripts/mumu-adb.sh")"
fi

export MAU_RUNS_DIR="${MAU_RUNS_DIR:-$ROOT/runs}"
exec "$MAU_MCP" "$@"
