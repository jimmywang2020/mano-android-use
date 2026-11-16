#!/usr/bin/env bash
# Resolve a usable MANO_DEVICE_SERIAL from live `adb devices`.
# Prints: export MANO_DEVICE_SERIAL=...
# Status on stderr. Intended for: eval "$(bash scripts/resolve-adb-serial.sh)"
#
# Priority:
#   1) Existing MANO_DEVICE_SERIAL if still state=device
#   2) Wireless ip:port (prefer numeric host:port over mDNS names)
#   3) USB / other serials in device state
#   4) MuMu probe (scripts/mumu-adb.sh)
#
# Compatible with macOS system bash 3.2 (no mapfile).
set -uo pipefail

_is_device() {
  local s="$1"
  [[ -n "$s" ]] || return 1
  local state
  state="$(adb -s "$s" get-state 2>/dev/null || true)"
  [[ "$state" == "device" ]]
}

adb start-server >/dev/null 2>&1 || true

if [[ -n "${MANO_DEVICE_SERIAL:-}" ]] && _is_device "$MANO_DEVICE_SERIAL"; then
  echo "KEEP ${MANO_DEVICE_SERIAL}" >&2
  echo "export MANO_DEVICE_SERIAL=${MANO_DEVICE_SERIAL}"
  exit 0
fi

if [[ -n "${MANO_DEVICE_SERIAL:-}" ]]; then
  echo "STALE ${MANO_DEVICE_SERIAL} (not device) — re-resolving" >&2
fi

pick=""
ip_pick=""
other_pick=""

while IFS= read -r line; do
  # "serial<TAB/SPACE>device ..."
  serial="$(echo "$line" | awk '{print $1}')"
  state="$(echo "$line" | awk '{print $2}')"
  [[ "$state" == "device" && -n "$serial" ]] || continue
  if [[ "$serial" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+$ ]]; then
    if [[ -z "$ip_pick" ]]; then
      ip_pick="$serial"
    fi
  elif [[ -z "$other_pick" ]]; then
    other_pick="$serial"
  fi
done < <(adb devices 2>/dev/null | awk 'NR>1 {print}')

if [[ -n "$ip_pick" ]]; then
  pick="$ip_pick"
elif [[ -n "$other_pick" ]]; then
  pick="$other_pick"
fi

if [[ -n "$pick" ]] && _is_device "$pick"; then
  echo "PICKED ${pick}" >&2
  echo "export MANO_DEVICE_SERIAL=${pick}"
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/mumu-adb.sh" ]]; then
  echo "No phone serial in adb devices; trying MuMu…" >&2
  mumu_out="$(bash "$SCRIPT_DIR/mumu-adb.sh" 2>/dev/null || true)"
  mumu_serial="$(echo "$mumu_out" | sed -n 's/^export MANO_DEVICE_SERIAL=//p' | tail -1)"
  if [[ -n "$mumu_serial" ]] && _is_device "$mumu_serial"; then
    echo "PICKED MuMu ${mumu_serial}" >&2
    echo "export MANO_DEVICE_SERIAL=${mumu_serial}"
    exit 0
  fi
fi

echo "No adb device in state=device. Pair/connect the phone or start MuMu." >&2
exit 1
