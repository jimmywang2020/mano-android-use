"""Host/agent tips surfaced by ready / android_run (not Core concerns)."""

from __future__ import annotations

from typing import Any

# Short playbook echoed into MCP/CLI JSON so hosts see it without opening docs.
PLAYBOOK_LINES: tuple[str, ...] = (
    "Prefer package=/launch_app when the target app is installed; avoid browser+中文 type.",
    "Call ready before Chinese type_text; if text_backend.available is false, install OpenATX AdbKeyboard.",
    "APK install / ColorOS「继续安装」dialogs: use observe+tap or a human — not android_run.",
    "Keep the screen awake and unlocked; wireless ADB ports change — refresh MANO_DEVICE_SERIAL.",
    "NEED_HUMAN / BLOCKED_BY_POLICY on payment UI is expected; do not force taps.",
)


def build_tips(
    *,
    screen: dict[str, Any] | None = None,
    text_backend: dict[str, Any] | None = None,
    include_playbook: bool = True,
) -> list[str]:
    tips: list[str] = []
    if include_playbook:
        tips.extend(PLAYBOOK_LINES)
    if screen and not screen.get("awake"):
        tips.insert(
            0,
            "Screen appears off/asleep. Wake the device (mau tries KEYCODE_WAKEUP once) "
            "and unlock before observe/android_run.",
        )
    if text_backend is not None and text_backend.get("available") is False:
        tips.insert(
            0,
            "Unicode IME unavailable — launch/tap/swipe OK; Chinese type_text will fail "
            "until OpenATX AdbKeyboard (com.github.uiautomator/.AdbKeyboard) is installed.",
        )
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
