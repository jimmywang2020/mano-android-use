"""MCP A′ server: host orchestrates; grounder sees screenshots; L0 executes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .envfile import load_dotenv
from .grounder import Grounder, pixel_from_normalized
from .session import DeviceSession

load_dotenv()

mcp = MCPServer("mano-android-use")

_SESSION: DeviceSession | None = None


def _session() -> DeviceSession:
    global _SESSION
    if _SESSION is None:
        _SESSION = DeviceSession.open(
            os.getenv("MANO_DEVICE_SERIAL") or None,
            runs_root=os.getenv("MAU_RUNS_DIR", "runs"),
        )
    return _SESSION


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def doctor() -> str:
    """Diagnose adb binary, serial, and device reachability (read-only).

    Agent tips: confirm serial matches the phone (wireless ports change). Call ready
    next for IME + screen + playbook tips. See docs/agent-playbook.md.
    """
    return _dumps(_session().doctor())


@mcp.tool()
def ready() -> str:
    """Doctor + screen wakefulness + Unicode IME preflight + agent tips.

    Returns JSON with screen, text_backend, tips[]. Chinese type_text needs OpenATX
    AdbKeyboard; launch/tap work without it. Prefer package=/launch_app over
    browser+中文. Keep screen awake/unlocked. Full playbook: docs/agent-playbook.md.
    """
    return _dumps(_session().ready())


@mcp.tool()
def observe(detail: str = "tree", max_nodes: int = 80) -> str:
    """Observe the device UI.

    detail=tree (default): compact accessibility tree + short summary, NO screenshot
    bytes for the host. Screenshots are still saved for the grounder/journal.
    detail=screenshot|both: also mark screenshot path for host debugging only.
    """
    if detail not in {"tree", "screenshot", "both"}:
        detail = "tree"
    return _dumps(_session().observe(detail=detail, max_nodes=max_nodes))


@mcp.tool()
def find(query: str, limit: int = 10) -> str:
    """Find UI nodes by substring in text/content-desc/resource-id (no VLM)."""
    return _dumps(_session().find(query, limit=limit))


@mcp.tool()
def launch_app(package: str) -> str:
    """Cold-start an Android package (force-stop then launch).

    Prefer this (or android_run package=) when the app is installed — e.g.
    tv.danmaku.bili for 哔哩哔哩 — instead of typing Chinese in a browser.
    """
    return _dumps(_session().launch(package))


@mcp.tool()
def tap(x: int, y: int, semantic_hint: str = "") -> str:
    """Tap at pixel coordinates. Optional semantic_hint helps the safety gateway."""
    return _dumps(_session().tap(int(x), int(y), semantic_hint=semantic_hint))


@mcp.tool()
def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 700, semantic_hint: str = "") -> str:
    """Swipe from (x1,y1) to (x2,y2) in pixels."""
    return _dumps(
        _session().swipe(
            int(x1), int(y1), int(x2), int(y2), duration_ms=int(duration_ms), semantic_hint=semantic_hint
        )
    )


@mcp.tool()
def type_text(text: str, semantic_hint: str = "") -> str:
    """Type text via the configured IME backend (Unicode needs AdbKeyboard)."""
    return _dumps(_session().type_text(text, semantic_hint=semantic_hint))


@mcp.tool()
def press_button(button: str) -> str:
    """Press a whitelisted system button: BACK, HOME, ENTER, CLEAR."""
    return _dumps(_session().press(button))


@mcp.tool()
def propose_action(instruction: str, model: str = "", execute: bool = False) -> str:
    """Ask the GUI grounder (gui-plus or glm-4.6v-flash) what to do next.

    The host should NOT look at screenshots; this tool sends the on-disk screenshot
    to the configured grounder model and returns a normalized action JSON.
    If execute=true, runs the action through the safety gateway + ADB.
    """
    session = _session()
    if not session.last_xml or session.last_size == (0, 0):
        obs = session.observe(detail="tree")
        image = Path(obs["screenshot_path"])
    else:
        # Re-observe for a fresh frame before grounding.
        obs = session.observe(detail="tree")
        image = Path(obs["screenshot_path"])

    grounder = Grounder(model or None)
    result = grounder.propose(image, instruction)
    out = result.to_dict()
    out["observation_step"] = obs.get("step")
    out["package"] = obs.get("package")
    if not result.ok or not result.action:
        return _dumps(out)

    mapped = pixel_from_normalized(result.action, session.last_size[0], session.last_size[1])
    out["mapped"] = mapped
    if execute:
        kind = result.action.get("action")
        if kind == "click" and "pixel" in mapped:
            x, y = mapped["pixel"]
            out["execution"] = session.tap(
                x, y, semantic_hint=instruction[:120]
            )
        elif kind == "swipe" and "pixel" in mapped and "pixel2" in mapped:
            x1, y1 = mapped["pixel"]
            x2, y2 = mapped["pixel2"]
            out["execution"] = session.swipe(x1, y1, x2, y2, semantic_hint=instruction[:120])
        elif kind == "type":
            out["execution"] = session.type_text(str(result.action.get("text") or ""))
        elif kind in {"system_button", "key"}:
            btn = str(result.action.get("button") or result.action.get("text") or "BACK")
            out["execution"] = session.press(btn)
        elif kind == "terminate":
            out["execution"] = {"ok": True, "terminated": True, "status": result.action.get("status")}
        else:
            out["execution"] = {"ok": False, "code": "UNSUPPORTED", "reason": f"kind={kind}"}
    return _dumps(out)


@mcp.tool()
def journal_tail(n: int = 20) -> str:
    """Return the last N journal events for this session."""
    return _dumps(_session().journal_tail(int(n)))


@mcp.tool()
def android_run(
    goal: str,
    max_steps: int = 25,
    model: str = "",
    package: str = "",
    success_package: str = "",
    success_labels_any: str = "",
    success_labels_all: str = "",
) -> str:
    """B-path: bounded observe→propose→act loop toward a natural-language goal.

    Playbook for hosts:
    - Known app → set package= (e.g. ctrip.android.view); avoid browser+中文 search.
    - Optional success_check: success_package + success_labels_any/all (comma-separated).
      Early-stops when the screen matches; vetoes false terminate:success.
    - Tries KEYCODE_WAKEUP once if asleep; still off → NEED_HUMAN (unlock manually).
    - Chinese typing needs AdbKeyboard (see ready.tips); install dialogs are not this tool.
    - Stops on payment/submit (NEED_HUMAN / BLOCKED_BY_POLICY), stuck, budget, errors.
    See docs/agent-playbook.md and docs/examples/ctrip-beijing-homestay.md.
    """
    from .run_loop import android_run as _android_run
    from .success_check import SuccessCheck

    def _split(raw: str) -> list[str]:
        return [p.strip() for p in (raw or "").split(",") if p.strip()]

    check = SuccessCheck(
        package=success_package.strip() or None,
        labels_any=_split(success_labels_any),
        labels_all=_split(success_labels_all),
    )
    result = _android_run(
        _session(),
        goal,
        max_steps=int(max_steps),
        model=model or None,
        package=package or None,
        success_check=None if check.is_empty() else check,
    )
    return _dumps(result.to_dict())


@mcp.tool()
def android_run_plan(plan_path: str = "", plan_json: str = "", model: str = "") -> str:
    """Run a staged plan (generic A/B/C): sequential android_run + per-stage success_check.

    App-agnostic — Ctrip homestay and Meituan takeout differ only by plan data.
    Provide either plan_path (repo-relative or absolute JSON) or plan_json (raw JSON).
    Examples: docs/examples/plans/ctrip-beijing-homestay.json,
    docs/examples/plans/meituan-guotiao-takeout.json.
    """
    import json
    from pathlib import Path

    from .run_loop import TERMINAL_OK
    from .run_plan import RunStage, android_run_plan, load_plan

    if plan_path.strip():
        path = Path(plan_path.strip())
        if not path.is_file():
            # Allow repo-relative paths when MCP cwd differs
            root = Path(__file__).resolve().parents[2]
            alt = root / plan_path.strip()
            path = alt if alt.is_file() else path
        plan_id, stages = load_plan(path)
    elif plan_json.strip():
        data = json.loads(plan_json)
        plan_id = str(data.get("id") or data.get("name") or "plan")
        stages = [RunStage.from_mapping(s) for s in (data.get("stages") or [])]
    else:
        return _dumps(
            {
                "status": "ERROR",
                "reason": "provide plan_path or plan_json",
            }
        )

    result = android_run_plan(
        _session(), stages, plan_id=plan_id, model=model or None
    )
    out = result.to_dict()
    out["ok"] = result.status == TERMINAL_OK
    return _dumps(out)


def main() -> None:
    # stdio transport for Cursor / Codex MCP hosts.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
