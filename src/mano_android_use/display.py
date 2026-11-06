"""Display / wakefulness helpers for Consumer-side preflight (not Pack/Core)."""

from __future__ import annotations

import re
import time
from typing import Any, Protocol


class _AdbShell(Protocol):
    def shell(self, *args: str) -> str: ...


_WAKEFULNESS_RE = re.compile(r"mWakefulness=(\w+)", re.I)


def parse_wakefulness(dumpsys_power: str) -> str:
    """Return wakefulness token: Awake / Asleep / Dreaming / Dozing / unknown."""
    match = _WAKEFULNESS_RE.search(dumpsys_power or "")
    if not match:
        return "unknown"
    return match.group(1)


def screen_state(adb: _AdbShell) -> dict[str, Any]:
    """Probe whether the display is awake via ``dumpsys power``."""
    try:
        raw = adb.shell("dumpsys", "power")
    except Exception as exc:  # noqa: BLE001
        return {
            "awake": False,
            "wakefulness": "unknown",
            "ok": False,
            "error": str(exc)[:300],
        }
    wake = parse_wakefulness(raw)
    awake = wake.lower() == "awake"
    return {
        "awake": awake,
        "wakefulness": wake,
        "ok": True,
        "error": None,
    }


def ensure_awake(adb: _AdbShell, *, auto_wake: bool = True, settle_s: float = 0.6) -> dict[str, Any]:
    """Return screen state; optionally send KEYCODE_WAKEUP once if asleep."""
    state = screen_state(adb)
    state["woke"] = False
    if state.get("awake") or not auto_wake:
        return state
    try:
        adb.shell("input", "keyevent", "KEYCODE_WAKEUP")
        state["woke"] = True
    except Exception as exc:  # noqa: BLE001
        state["wake_error"] = str(exc)[:300]
        return state
    time.sleep(max(settle_s, 0.0))
    again = screen_state(adb)
    again["woke"] = True
    again["wakefulness_before"] = state.get("wakefulness")
    return again
