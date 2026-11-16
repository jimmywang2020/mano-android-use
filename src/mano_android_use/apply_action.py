"""Apply a normalized grounder action through L0 DeviceSession.

Single dispatcher for android_run and (legacy) propose_action(execute=…).
All device hits should go through session.tap/swipe/type_text/press (or wait).
"""

from __future__ import annotations

import time
from typing import Any

VIA_ANDROID_RUN = "android_run"
VIA_PROPOSE_EXECUTE = "propose_execute"
VIA_L0_DIRECT = "l0_direct"


def normalize_kind(action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map grounder aliases to canonical kinds; may copy button_name → button."""
    kind = str(action.get("action") or "")
    # gui-plus sometimes emits system_button_press + button_name (ColorOS runs).
    if kind in {"system_button_press", "press", "keyevent"}:
        kind = "system_button"
        if "button" not in action and action.get("button_name"):
            action = {**action, "button": action.get("button_name")}
    return kind, action


def apply_action(
    session: Any,
    action: dict[str, Any],
    mapped: dict[str, Any] | None = None,
    *,
    semantic_hint: str = "",
    via: str = VIA_ANDROID_RUN,
) -> dict[str, Any]:
    """Execute one grounder action on ``session``.

    ``mapped`` should already include pixel / pixel2 from ``pixel_from_normalized``
    when the action needs coordinates.
    """
    mapped = mapped or {}
    kind, action = normalize_kind(action)
    hint = (semantic_hint or "")[:120]

    if kind == "click" and "pixel" in mapped:
        x, y = mapped["pixel"]
        return session.tap(int(x), int(y), semantic_hint=hint, via=via)
    if kind == "swipe" and "pixel" in mapped and "pixel2" in mapped:
        x1, y1 = mapped["pixel"]
        x2, y2 = mapped["pixel2"]
        return session.swipe(
            int(x1), int(y1), int(x2), int(y2), semantic_hint=hint, via=via
        )
    if kind == "type":
        return session.type_text(str(action.get("text") or ""), semantic_hint=hint, via=via)
    if kind in {"system_button", "key"}:
        btn = str(
            action.get("button")
            or action.get("button_name")
            or action.get("text")
            or "BACK"
        )
        return session.press(btn, via=via)
    if kind == "wait":
        time.sleep(min(max(float(action.get("time") or 1), 0.2), 5.0))
        return {"ok": True, "waited": True, "via": via}
    if kind == "terminate":
        return {
            "ok": True,
            "terminated": True,
            "status": action.get("status"),
            "via": via,
        }
    return {"ok": False, "code": "UNSUPPORTED", "reason": f"kind={kind}", "via": via}
