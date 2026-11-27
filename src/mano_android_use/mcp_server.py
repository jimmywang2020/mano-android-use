"""MCP server: Host picks goal/plan; mau may orchestrate; Grounder sees shots; L0 executes."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .apply_action import VIA_L0_DIRECT, VIA_PROPOSE_EXECUTE, apply_action
from .envfile import load_dotenv
from .grounder import Grounder, pixel_from_normalized
from .session import DeviceSession
from .trace_report import (
    EVENT_PROPOSE_STEP,
    build_step_span,
    cost_report_from_doc,
)

load_dotenv()

mcp = MCPServer("mano-android-use")

# Soft wall-clock budget for MCP so Host -32001 empty timeouts are less likely.
# CLI keeps larger max_steps and wall_budget_ms=0 by default.
_MCP_WALL_BUDGET_MS = 90_000
_MCP_DEFAULT_MAX_STEPS = 10

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


def _propose_execute_allowed() -> bool:
    return os.getenv("MAU_ALLOW_PROPOSE_EXECUTE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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
    """Observe the device UI (on-demand capture).

    detail=tree (default): accessibility dump only (no PNG) + compact tree/summary.
    detail=screenshot: PNG only (keeps last XML in session).
    detail=both: full capture (screenshot + XML). Prefer android_run for multi-step goals;
    it gates on tree and upgrades to shot/full only before VLM.
    """
    if detail not in {"tree", "screenshot", "both"}:
        detail = "tree"
    return _dumps(_session().observe(detail=detail, max_nodes=max_nodes))


@mcp.tool()
def find(query: str, limit: int = 10) -> str:
    """Find UI nodes by substring in text/content-desc/resource-id (no VLM).

    Correction/debug only — for multi-step goals prefer android_run / android_run_plan.
    """
    return _dumps(_session().find(query, limit=limit))


@mcp.tool()
def launch_app(package: str) -> str:
    """Cold-start an Android package (force-stop then launch).

    Prefer this (or android_run package=) when the app is installed — e.g.
    tv.danmaku.bili for 哔哩哔哩 — instead of typing Chinese in a browser.
    """
    return _dumps(_session().launch(package))


@mcp.tool()
def tap(x: int, y: int, semantic_hint: str = "", force_l0: bool = False) -> str:
    """L0 correction: tap pixel coordinates. Optional semantic_hint for safety.

    Prefer android_run / android_run_plan for multi-step goals. Use tap for install
    dialogs, known tree hits after find, or when the run loop needs a human/host nudge.

    After android_run STUCK, Host L0 has quota=1 then returns L0_BLOCKED_AFTER_STUCK
    unless force_l0=true (Phase R). Prefer find → short android_run over L0 chains.
    """
    return _dumps(
        _session().tap(
            int(x),
            int(y),
            semantic_hint=semantic_hint,
            via=VIA_L0_DIRECT,
            force_l0=bool(force_l0),
        )
    )


@mcp.tool()
def swipe(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 700,
    semantic_hint: str = "",
    force_l0: bool = False,
) -> str:
    """L0 correction: swipe from (x1,y1) to (x2,y2) in pixels.

    After STUCK, same Phase R L0 quota / force_l0 as tap.
    """
    return _dumps(
        _session().swipe(
            int(x1),
            int(y1),
            int(x2),
            int(y2),
            duration_ms=int(duration_ms),
            semantic_hint=semantic_hint,
            via=VIA_L0_DIRECT,
            force_l0=bool(force_l0),
        )
    )


@mcp.tool()
def type_text(text: str, semantic_hint: str = "", force_l0: bool = False) -> str:
    """L0 correction: type text via IME (Unicode needs AdbKeyboard).

    After STUCK, same Phase R L0 quota / force_l0 as tap.
    """
    return _dumps(
        _session().type_text(
            text,
            semantic_hint=semantic_hint,
            via=VIA_L0_DIRECT,
            force_l0=bool(force_l0),
        )
    )


@mcp.tool()
def press_button(button: str, force_l0: bool = False) -> str:
    """L0 correction: press BACK, HOME, ENTER, or CLEAR.

    After STUCK, same Phase R L0 quota / force_l0 as tap. Do not chain BACK to recover STUCK.
    """
    return _dumps(
        _session().press(button, via=VIA_L0_DIRECT, force_l0=bool(force_l0))
    )


@mcp.tool()
def propose_action(instruction: str, model: str = "", execute: bool = False) -> str:
    """Debug/single-step: ask Grounder what to do next (does not replace android_run).

    Host should NOT look at screenshots; this tool sends the on-disk screenshot to
    the configured grounder and returns normalized action JSON + mapped pixels.

    Default path for goals: android_run or android_run_plan.
    execute=true is DEPRECATED — ignored unless MAU_ALLOW_PROPOSE_EXECUTE=1.
    Prefer android_run (orchestration) or L0 tap/swipe/type/press (correction).
    Returns timing + cost_fragment (propose_step journal span).
    """
    session = _session()
    t0 = time.perf_counter()
    obs = session.observe(detail="tree")
    observe_ms = int((time.perf_counter() - t0) * 1000)
    image = Path(obs["screenshot_path"])

    grounder = Grounder(model or None)
    t1 = time.perf_counter()
    result = grounder.propose(image, instruction)
    grounder_ms = int(result.latency_ms or ((time.perf_counter() - t1) * 1000))
    out = result.to_dict()
    out["observation_step"] = obs.get("step")
    out["package"] = obs.get("package")

    via = "propose"
    act_ms = 0
    action_name = ""
    if result.ok and result.action:
        action_name = str(result.action.get("action") or "")
        mapped = pixel_from_normalized(
            result.action, session.last_size[0], session.last_size[1]
        )
        out["mapped"] = mapped
        if execute:
            out["execute_deprecated"] = True
            if not _propose_execute_allowed():
                out["execution"] = {
                    "ok": False,
                    "code": "EXECUTE_DEPRECATED",
                    "reason": (
                        "propose_action(execute=true) is deprecated; use android_run or "
                        "L0 tap/swipe/type/press. Set MAU_ALLOW_PROPOSE_EXECUTE=1 to force."
                    ),
                    "via": VIA_PROPOSE_EXECUTE,
                }
            else:
                via = VIA_PROPOSE_EXECUTE
                t2 = time.perf_counter()
                out["execution"] = apply_action(
                    session,
                    result.action,
                    mapped,
                    semantic_hint=instruction[:120],
                    via=VIA_PROPOSE_EXECUTE,
                )
                act_ms = int((time.perf_counter() - t2) * 1000)

    timing = build_step_span(
        step=int(obs.get("step") or session.step or 0),
        model=grounder.model,
        observe_ms=observe_ms,
        grounder_ms=grounder_ms,
        act_ms=act_ms,
        prompt_tokens=int(result.prompt_tokens or 0),
        completion_tokens=int(result.completion_tokens or 0),
        grounder_calls=int(result.call_count or 1),
        action=action_name,
        via=via,
        event=EVENT_PROPOSE_STEP,
    )
    session.log_event(dict(timing))
    out["timing"] = timing
    out["cost_fragment"] = cost_report_from_doc(
        {"steps": [timing], "totals": None}
    )
    return _dumps(out)


@mcp.tool()
def journal_tail(n: int = 20) -> str:
    """Return the last N journal events for this session."""
    return _dumps(_session().journal_tail(int(n)))


@mcp.tool()
def slot_peek(slots_path: str, progress_json: str = "") -> str:
    """Phase P4/O3: next SlotSpec + android_run args + suggested find needles.

    Read-only (no device). After STUCK/TIME_BUDGET: find(suggested_find) →
    replace tree_hints if page wrong → short android_run from args.mcp_arguments
    (omit package when warm). Example slots_path:
    docs/examples/slots/meituan-dual-drink.slots.json
    """
    from .host_slots import load_slot_graph, slot_peek as _peek

    path = (slots_path or "").strip()
    if not path:
        return _dumps({"ok": False, "code": "MISSING_SLOTS_PATH"})
    prog: dict = {}
    raw = (progress_json or "").strip()
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                prog = loaded
        except json.JSONDecodeError as exc:
            return _dumps({"ok": False, "code": "BAD_PROGRESS_JSON", "reason": str(exc)})
    try:
        graph = load_slot_graph(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _dumps({"ok": False, "code": "SLOT_LOAD_ERROR", "reason": str(exc)})
    out = _peek(graph, prog)
    out["ok"] = True
    out["graph_id"] = graph.id
    return _dumps(out)


@mcp.tool()
def resume_from_run(
    run_id: str = "",
    slots_path: str = "",
    goal: str = "",
) -> str:
    """Phase O-B: after Cursor -32001 / empty timeout, draft TaskState from journal.

    Does not touch the device. Prefer this before guessing goals. cart_count comes
    only from「已添加N件」a11y text — never from GOAL_REACHED event counts.
    Confirm needs_confirm fields, then short android_run with mcp_hint
    (omit package, cold_start=false, progress_json). Optional slots_path
    (e.g. docs/examples/slots/meituan-dual-drink.slots.json) suggests
    completed_slots heuristically. Empty run_id → newest under session runs root.
    """
    from .resume_from_run import resume_from_run as _resume

    session = _session()
    runs_root = str(Path(session.run_dir).parent)
    target = run_id.strip() or None
    out = _resume(
        target,
        runs_root=runs_root,
        slots_path=slots_path.strip() or None,
        goal=goal or "",
    )
    return _dumps(out)


@mcp.tool()
def android_run(
    goal: str,
    max_steps: int = _MCP_DEFAULT_MAX_STEPS,
    model: str = "",
    package: str = "",
    success_package: str = "",
    success_labels_any: str = "",
    success_labels_all: str = "",
    success_forbid_labels: str = "",
    tree_hints: str = "",
    stuck_same_summary: int = -1,
    cold_start: bool = False,
    progress_json: str = "",
) -> str:
    """PRIMARY: bounded observe→propose→act loop toward a natural-language goal.

    Host picks the goal; mau orchestrates the loop; Grounder sees screenshots; L0 acts.
    MCP defaults: max_steps=10, wall soft-budget ~90s → may return TIME_BUDGET +
    cost_report + continue_hint/resume + **task_patch** (merge into Host TaskState;
    re-call short android_run; do not switch to L0 loop).
    Unchanged screen (default): skip VLM, recover once (BACK) then STUCK — but not
    for a few steps after type (search IME grace).
    tree_hints: comma-separated labels for tree-first tap before VLM (also uses「quoted」in goal).
    package=: warm-ensure by default (no force-stop if already foreground). Set
    cold_start=true only for a true relaunch. On TIME_BUDGET resume, omit package=
    or keep cold_start=false, and pass progress_json from TaskState.progress
    (OR-seed; mau does not persist Host TaskState).
    Long jobs: multiple short MCP calls or CLI `mau run` / `mau run-plan`.
    Response includes cost_report: total_ms, tokens, by_phase, vlm_skipped, by_via,
    per_step, and narrative — always relay cost_report.narrative (+ dominant_phase) to the user.
    Playbook:
    - Known app → set package= (e.g. ctrip.android.view); avoid browser+中文 search.
    - Optional success_check: success_package + success_labels_any/all +
      success_forbid_labels (comma-separated; e.g. 请输入终点). Prefer labels_all
      for terminal stages. Early-stops when the screen matches; vetoes false terminate:success.
    - Long / multi-stage in Cursor → N× short android_run (slots); android_run_plan mainly CLI.
    - Tries KEYCODE_WAKEUP once if asleep; still off → NEED_HUMAN (unlock manually).
    - Chinese typing needs AdbKeyboard (see ready.tips); install dialogs are not this tool.
    - Stops on payment/submit (NEED_HUMAN / BLOCKED_BY_POLICY), stuck, budget, TIME_BUDGET, errors.
    See docs/agent-playbook.md and docs/examples/ctrip-beijing-homestay.md.
    """
    from .run_loop import android_run as _android_run
    from .run_loop import parse_progress_json
    from .success_check import SuccessCheck

    def _split(raw: str) -> list[str]:
        return [p.strip() for p in (raw or "").split(",") if p.strip()]

    check = SuccessCheck(
        package=success_package.strip() or None,
        labels_any=_split(success_labels_any),
        labels_all=_split(success_labels_all),
        forbid_labels=_split(success_forbid_labels),
    )
    stuck_arg = None if int(stuck_same_summary) < 0 else int(stuck_same_summary)
    try:
        seeded = parse_progress_json(progress_json)
    except Exception as exc:  # noqa: BLE001 — surface bad Host JSON clearly
        return _dumps({"status": "ERROR", "reason": f"progress_json: {exc}"})
    result = _android_run(
        _session(),
        goal,
        max_steps=int(max_steps),
        model=model or None,
        package=package or None,
        success_check=None if check.is_empty() else check,
        wall_budget_ms=_MCP_WALL_BUDGET_MS,
        tree_hints=_split(tree_hints),
        stuck_same_summary=stuck_arg,
        cold_start=bool(cold_start),
        initial_progress=seeded or None,
    )
    return _dumps(result.to_dict())


@mcp.tool()
def android_run_plan(plan_path: str = "", plan_json: str = "", model: str = "") -> str:
    """Staged plan = sequential android_run + per-stage success_check.

    Cursor multi-stage (Meituan dual-drink, DiDi fare, …): prefer N× short android_run
    via SlotSpec (docs/examples/slots/) so each call stays under Host timeout — one fat
    MCP plan often hits -32001. Prefer this tool for CLI `mau run-plan` or already-short
    plans. App-agnostic — apps differ only by plan data. Provide plan_path or plan_json.
    Each stage uses ~90s MCP wall soft-budget; TIME_BUDGET stops later stages and returns
    partial cost_report + continue_hint. Always relay cost_report.narrative + per-stage
    dominant_phase. Examples: docs/examples/plans/ctrip-beijing-homestay.json,
    docs/examples/plans/meituan-dual-drink-cart.json (still better as short runs in Cursor).
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
        _session(),
        stages,
        plan_id=plan_id,
        model=model or None,
        wall_budget_ms=_MCP_WALL_BUDGET_MS,
    )
    out = result.to_dict()
    out["ok"] = result.status == TERMINAL_OK
    return _dumps(out)


def main() -> None:
    # stdio transport for Cursor / Codex MCP hosts.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
