"""CLI for L0 smoke: doctor / observe / tap / propose."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _print(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    from .envfile import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(prog="mau", description="mano-android-use CLI")
    parser.add_argument("--serial", default=os.getenv("MANO_DEVICE_SERIAL", ""))
    parser.add_argument("--runs", default=os.getenv("MAU_RUNS_DIR", "runs"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Check adb + device")
    sub.add_parser("ready", help="Doctor + text backend preflight")
    p_obs = sub.add_parser("observe", help="Capture compact tree (default no host screenshot)")
    p_obs.add_argument("--detail", choices=("tree", "screenshot", "both"), default="tree")
    p_find = sub.add_parser("find", help="Find nodes by substring")
    p_find.add_argument("query")
    p_tap = sub.add_parser("tap", help="Tap pixel coordinates")
    p_tap.add_argument("x", type=int)
    p_tap.add_argument("y", type=int)
    p_type = sub.add_parser("type", help="Type text")
    p_type.add_argument("text")
    p_press = sub.add_parser("press", help="Press BACK/HOME/ENTER")
    p_press.add_argument("button")
    p_launch = sub.add_parser("launch", help="Cold-start package")
    p_launch.add_argument("package")
    p_prop = sub.add_parser(
        "propose",
        help="Debug: one-shot Grounder (default: do not execute; prefer mau run)",
    )
    p_prop.add_argument("instruction")
    p_prop.add_argument("--model", default=os.getenv("MAU_GROUNDER_MODEL", ""))
    p_prop.add_argument("--image", default="", help="Existing PNG path; else observe first")
    p_prop.add_argument(
        "--execute",
        action="store_true",
        help="DEPRECATED: execute mapped action (requires MAU_ALLOW_PROPOSE_EXECUTE=1)",
    )
    p_run = sub.add_parser("run", help="PRIMARY: bounded android_run(goal) loop")
    p_run.add_argument("goal", help="Natural-language goal")
    p_run.add_argument("--max-steps", type=int, default=25)
    p_run.add_argument("--model", default=os.getenv("MAU_GROUNDER_MODEL", ""))
    p_run.add_argument(
        "--package",
        default="",
        help="Optional package to ensure before loop (warm by default; see --cold-start)",
    )
    p_run.add_argument(
        "--cold-start",
        action="store_true",
        help="With --package: force-stop then launch (default is warm ensure)",
    )
    p_run.add_argument(
        "--success-package",
        default="",
        help="success_check: require foreground package",
    )
    p_run.add_argument(
        "--success-label",
        action="append",
        default=[],
        dest="success_labels",
        help="success_check: labels_any substring (repeatable)",
    )
    p_run.add_argument(
        "--success-label-all",
        action="append",
        default=[],
        dest="success_labels_all",
        help="success_check: labels_all substring (repeatable)",
    )
    p_run.add_argument(
        "--tree-hint",
        action="append",
        default=[],
        dest="tree_hints",
        help="Tree-first find label before VLM (repeatable); also uses「quoted」in goal",
    )
    p_run.add_argument(
        "--stuck-same-summary",
        type=int,
        default=-1,
        help="Unchanged-screen threshold (default 3; 0=off). Skip VLM / recover / STUCK",
    )
    p_run.add_argument(
        "--wall-budget-ms",
        type=int,
        default=0,
        help="Soft wall budget (ms); 0=off. MCP-like resume demos use e.g. 45000",
    )
    p_run.add_argument(
        "--progress-json",
        default="",
        help='Host TaskState progress seed, e.g. \'{"fare_seen":true}\'',
    )
    p_plan = sub.add_parser(
        "run-plan",
        help="Run a staged plan JSON (generic A/B/C + per-stage success_check)",
    )
    p_plan.add_argument(
        "plan",
        help="Path to plan JSON (e.g. docs/examples/plans/ctrip-beijing-homestay.json)",
    )
    p_plan.add_argument("--model", default=os.getenv("MAU_GROUNDER_MODEL", ""))
    p_trace = sub.add_parser(
        "trace",
        help="Summarize android_run step timings/tokens from runs/<id> (trace.json / journal)",
    )
    p_trace.add_argument(
        "target",
        nargs="?",
        default="",
        help="Run dir, trace.json, or journal.jsonl (default: newest under --runs)",
    )
    p_trace.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print full trace JSON instead of a table",
    )

    args = parser.parse_args(argv)

    # Read-only: no device session required.
    if args.cmd == "trace":
        from .trace_report import format_trace_table, load_trace, resolve_trace_target

        try:
            run_dir = resolve_trace_target(args.target or None, runs_root=args.runs)
            doc = load_trace(run_dir)
        except FileNotFoundError as exc:
            _print({"ok": False, "code": "TRACE_NOT_FOUND", "reason": str(exc)})
            return 1
        if args.as_json:
            _print(doc)
        else:
            print(format_trace_table(doc))
        return 0

    from mano.errors import ManoError

    from .session import DeviceSession

    try:
        session = DeviceSession.open(args.serial or None, runs_root=args.runs)
    except ManoError as exc:
        _print({"ok": False, "code": "SESSION_ERROR", "reason": str(exc)})
        return 1

    if args.cmd == "doctor":
        info = session.doctor()
        _print(info)
        return 0 if info.get("ok") else 1
    if args.cmd == "ready":
        info = session.ready()
        _print(info)
        return 0 if info.get("ready") else 1
    if args.cmd == "observe":
        _print(session.observe(detail=args.detail))
        return 0
    if args.cmd == "find":
        _print(session.find(args.query))
        return 0
    if args.cmd == "tap":
        _print(session.tap(args.x, args.y))
        return 0
    if args.cmd == "type":
        _print(session.type_text(args.text))
        return 0
    if args.cmd == "press":
        _print(session.press(args.button))
        return 0
    if args.cmd == "launch":
        _print(session.launch(args.package))
        return 0
    if args.cmd == "propose":
        import time

        from .apply_action import VIA_PROPOSE_EXECUTE, apply_action
        from .grounder import Grounder, pixel_from_normalized
        from .trace_report import EVENT_PROPOSE_STEP, build_step_span, cost_report_from_doc

        observe_ms = 0
        if args.image:
            image = Path(args.image)
            # Ensure size known
            if session.last_size == (0, 0):
                t0 = time.perf_counter()
                session.observe(detail="tree")
                observe_ms = int((time.perf_counter() - t0) * 1000)
        else:
            t0 = time.perf_counter()
            obs = session.observe(detail="tree")
            observe_ms = int((time.perf_counter() - t0) * 1000)
            image = Path(obs["screenshot_path"])
        grounder = Grounder(args.model or None)
        t1 = time.perf_counter()
        result = grounder.propose(image, args.instruction)
        grounder_ms = int(result.latency_ms or ((time.perf_counter() - t1) * 1000))
        out = result.to_dict()
        mapped = None
        via = "propose"
        act_ms = 0
        action_name = ""
        if result.ok and result.action and session.last_size[0] > 0:
            action_name = str(result.action.get("action") or "")
            mapped = pixel_from_normalized(
                result.action, session.last_size[0], session.last_size[1]
            )
            out["mapped"] = mapped
        if args.execute:
            out["execute_deprecated"] = True
            allowed = os.getenv("MAU_ALLOW_PROPOSE_EXECUTE", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if not allowed:
                out["execution"] = {
                    "ok": False,
                    "code": "EXECUTE_DEPRECATED",
                    "reason": (
                        "mau propose --execute is deprecated; use mau run or L0 tap. "
                        "Set MAU_ALLOW_PROPOSE_EXECUTE=1 to force."
                    ),
                    "via": VIA_PROPOSE_EXECUTE,
                }
            elif result.ok and result.action and mapped is not None:
                via = VIA_PROPOSE_EXECUTE
                t2 = time.perf_counter()
                out["execution"] = apply_action(
                    session,
                    result.action,
                    mapped,
                    semantic_hint=args.instruction[:120],
                    via=VIA_PROPOSE_EXECUTE,
                )
                act_ms = int((time.perf_counter() - t2) * 1000)
        timing = build_step_span(
            step=session.step,
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
        out["cost_fragment"] = cost_report_from_doc({"steps": [timing]})
        _print(out)
        return 0 if result.ok else 1
    if args.cmd == "run":
        from .run_loop import TERMINAL_OK, android_run
        from .success_check import SuccessCheck

        check = SuccessCheck(
            package=args.success_package or None,
            labels_any=list(args.success_labels or []),
            labels_all=list(args.success_labels_all or []),
        )
        stuck_arg = None if int(args.stuck_same_summary) < 0 else int(args.stuck_same_summary)
        from .run_loop import parse_progress_json

        try:
            seeded = parse_progress_json(args.progress_json)
        except Exception as exc:  # noqa: BLE001
            _print({"status": "ERROR", "reason": f"progress_json: {exc}"})
            return 1
        result = android_run(
            session,
            args.goal,
            max_steps=args.max_steps,
            model=args.model or None,
            package=args.package or None,
            success_check=None if check.is_empty() else check,
            tree_hints=list(args.tree_hints or []),
            stuck_same_summary=stuck_arg,
            cold_start=bool(args.cold_start),
            wall_budget_ms=int(args.wall_budget_ms or 0),
            initial_progress=seeded or None,
        )
        _print(result.to_dict())
        return 0 if result.status == TERMINAL_OK else 1
    if args.cmd == "run-plan":
        from .run_loop import TERMINAL_OK
        from .run_plan import android_run_plan, load_plan

        plan_id, stages = load_plan(args.plan)
        result = android_run_plan(
            session, stages, plan_id=plan_id, model=args.model or None
        )
        _print(result.to_dict())
        return 0 if result.status == TERMINAL_OK else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
