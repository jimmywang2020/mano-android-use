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

    return 2


if __name__ == "__main__":
    sys.exit(main())
