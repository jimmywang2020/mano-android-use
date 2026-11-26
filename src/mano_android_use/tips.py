"""Host/agent tips surfaced by ready / android_run (not Core concerns)."""

from __future__ import annotations

from typing import Any

# Short playbook echoed into MCP/CLI JSON so hosts see it without opening docs.
PLAYBOOK_LINES: tuple[str, ...] = (
    "Default path (Cursor): ready → N× short android_run (one slot/stage each; host_slots). Prefer CLI mau run-plan for long plans — fat MCP android_run_plan often hits Host -32001. Do not chain propose_action for multi-step goals.",
    "MCP: keep each android_run short (default max_steps=10, ~90s soft budget). On TIME_BUDGET/STUCK: find(done_when) or slot_peek → replace tree_hints if page wrong → short resume (omit package=, cold_start=false). Do NOT recover STUCK with L0 tap/BACK chains (Phase Q). On -32001: resume_from_run → confirm 件数 → short resume. Never HOME/force_stop/rewrite_goal/L0 main loop.",
    "Goals: never include payment/submit button copy (e.g. 立即支付); stop-before-pay wording only. Meituan: A needs 选规格/请输入商品名 (not bare 点菜); dual-drink C/D need 已添加2件. Acquire hints SKU-first. Before C: find a visible second drink (奶茶 or another single cup) — never hardcode store SKU into slots. Short stages (搜 / 露菜单 / 规格加购).",
    "Unchanged screen: mau skips VLM (recover BACK once, then STUCK). tree_shortcut miss (no screen change / Guard NO_OP) falls through to VLM same step. Pass SKU-first tree_hints or「quoted」labels.",
    "Prefer package= (warm ensure) or launch_app (cold) when the app is installed; avoid browser+中文 type.",
    "Call ready before Chinese type_text; if text_backend.available is false, install OpenATX AdbKeyboard.",
    "APK install / ColorOS「继续安装」dialogs: use observe+tap or a human — not android_run.",
    "Keep the screen awake and unlocked; wireless ADB ports change — refresh MANO_DEVICE_SERIAL.",
    "NEED_HUMAN / BLOCKED_BY_POLICY on payment UI is expected; do not force taps.",
    "Optional faster observe: uv sync --extra u2 and MAU_OBSERVE_BACKEND=u2 (ADB fallback if agent down). Default remains ADB.",
)


def build_tips(
    *,
    screen: dict[str, Any] | None = None,
    text_backend: dict[str, Any] | None = None,
    observe_backend: dict[str, Any] | None = None,
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
    if (
        observe_backend is not None
        and observe_backend.get("requested") == "u2"
        and observe_backend.get("available") is False
    ):
        reason = str(observe_backend.get("reason") or "U2 unavailable")
        tips.insert(
            0,
            f"MAU_OBSERVE_BACKEND=u2 but agent unavailable ({reason[:160]}). "
            "observe will fall back to ADB until uiautomator2/atx-agent is healthy.",
        )
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
