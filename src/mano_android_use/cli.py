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
    p_prop = sub.add_parser("propose", help="Grounder propose_action on last/new screenshot")
    p_prop.add_argument("instruction")
    p_prop.add_argument("--model", default=os.getenv("MAU_GROUNDER_MODEL", ""))
    p_prop.add_argument("--image", default="", help="Existing PNG path; else observe first")
    p_run = sub.add_parser("run", help="B-path: bounded android_run(goal) loop")
    p_run.add_argument("goal", help="Natural-language goal")
    p_run.add_argument("--max-steps", type=int, default=25)
    p_run.add_argument("--model", default=os.getenv("MAU_GROUNDER_MODEL", ""))
    p_run.add_argument("--package", default="", help="Optional cold-start package before loop")
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
    p_plan = sub.add_parser(
        "run-plan",
        help="Run a staged plan JSON (generic A/B/C + per-stage success_check)",
    )
    p_plan.add_argument(
        "plan",
        help="Path to plan JSON (e.g. docs/examples/plans/ctrip-beijing-homestay.json)",
    )
    p_plan.add_argument("--model", default=os.getenv("MAU_GROUNDER_MODEL", ""))

    args = parser.parse_args(argv)

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
        from .grounder import Grounder, pixel_from_normalized

        if args.image:
            image = Path(args.image)
            # Ensure size known
            if session.last_size == (0, 0):
                session.observe(detail="tree")
        else:
            obs = session.observe(detail="tree")
            image = Path(obs["screenshot_path"])
        grounder = Grounder(args.model or None)
        result = grounder.propose(image, args.instruction)
        out = result.to_dict()
        if result.ok and result.action and session.last_size[0] > 0:
            out["mapped"] = pixel_from_normalized(
                result.action, session.last_size[0], session.last_size[1]
            )
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
        result = android_run(
            session,
            args.goal,
            max_steps=args.max_steps,
            model=args.model or None,
            package=args.package or None,
            success_check=None if check.is_empty() else check,
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
