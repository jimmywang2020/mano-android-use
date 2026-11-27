"""Phase R: block Host L0 main-loop after android_run STUCK.

Arm only on terminal STUCK (not TIME_BUDGET). Quota=1 direct L0; then require
``force_l0=True``. Orthogonal to SafetyGateway / Guard.
"""

from __future__ import annotations

from typing import Any

CODE_L0_BLOCKED_AFTER_STUCK = "L0_BLOCKED_AFTER_STUCK"
EVENT_L0_BLOCKED = "l0_blocked_after_stuck"
EVENT_L0_FORCE = "l0_force_after_stuck"
EVENT_GATE_ARM = "orchestration_gate_arm"
EVENT_GATE_DISARM = "orchestration_gate_disarm"

# Terminal status that arms the gate (run_loop.TERMINAL_STUCK).
STATUS_STUCK = "STUCK"

DEFAULT_L0_AFTER_STUCK_QUOTA = 1

_NEXT_AFTER_BLOCK: list[str] = [
    "find",
    "slot_peek",
    "android_run",
]


def blocked_payload(*, remaining: int = 0) -> dict[str, Any]:
    """Stable deny body for MCP/CLI Hosts."""
    return {
        "ok": False,
        "allow": False,
        "code": CODE_L0_BLOCKED_AFTER_STUCK,
        "reason": (
            "Host L0 blocked after android_run STUCK (quota exhausted). "
            "Use find/slot_peek → replace tree_hints → short android_run; "
            "or pass force_l0=true for one explicit correction."
        ),
        "remaining": int(remaining),
        "next": list(_NEXT_AFTER_BLOCK),
        "do": {
            "tool": "android_run",
            "omit_package": True,
            "cold_start": False,
            "hint": "find or slot_peek first; replace tree_hints; short resume",
        },
    }
