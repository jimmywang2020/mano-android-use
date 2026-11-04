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
    """Diagnose adb binary, serial, and device reachability (read-only)."""
    return _dumps(_session().doctor())


@mcp.tool()
def ready() -> str:
    """Ensure device session is ready (doctor + text backend preflight)."""
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
    """Cold-start an Android package (force-stop then launch)."""
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
) -> str:
    """B-path: run a bounded observe→propose→act loop toward a natural-language goal.

    Uses the same L0 session, safety gateway, and GUI grounder as the fine-grained
    tools. Prefer this when the host should not orchestrate every tap. Stops on
    payment/submit screens, policy blocks, repeated actions, errors, or budget.
    """
    from .run_loop import android_run as _android_run

    result = _android_run(
        _session(),
        goal,
        max_steps=int(max_steps),
        model=model or None,
        package=package or None,
    )
    return _dumps(result.to_dict())


def main() -> None:
    # stdio transport for Cursor / Codex MCP hosts.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
