"""B-path: bounded android_run(goal) loop without LangGraph.

Reuses DeviceSession + Grounder + SafetyGateway. Host/CLI passes a goal; the
service observes, proposes, guards, and acts until a terminal status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .grounder import Grounder, pixel_from_normalized
from .session import DeviceSession


TERMINAL_OK = "GOAL_REACHED"
TERMINAL_HUMAN = "NEED_HUMAN"
TERMINAL_BLOCKED = "BLOCKED_BY_POLICY"
TERMINAL_STUCK = "STUCK"
TERMINAL_BUDGET = "BUDGET_EXCEEDED"
TERMINAL_ERROR = "ERROR"


@dataclass
class RunResult:
    status: str
    goal: str
    steps: int
    model: str
    run_id: str
    run_dir: str
    last_summary: str = ""
    package: str = ""
    reason: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "goal": self.goal,
            "steps": self.steps,
            "model": self.model,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "last_summary": self.last_summary,
            "package": self.package,
            "reason": self.reason,
            "history": self.history,
        }


def _action_fingerprint(action: dict[str, Any] | None, mapped: dict[str, Any] | None) -> str:
    if not action:
        return "none"
    kind = str(action.get("action") or "")
    if mapped and "pixel" in mapped:
        return f"{kind}:{mapped.get('pixel')}:{mapped.get('pixel2')}"
    return f"{kind}:{action.get('coordinate')}:{action.get('text')}:{action.get('button')}"


def _instruction(goal: str, summary: str, step: int, max_steps: int) -> str:
    return (
        f"User goal: {goal}\n"
        f"Step {step}/{max_steps}. Current screen summary: {summary}\n"
        "Propose the single next UI action toward the goal. "
        "If the goal is already achieved, return "
        '{"action":"terminate","status":"success"}. '
        "Never pay, confirm payment, or submit an order."
    )


def android_run(
    session: DeviceSession,
    goal: str,
    *,
    max_steps: int = 25,
    model: str | None = None,
    package: str | None = None,
    stuck_repeat: int = 3,
) -> RunResult:
    """Run a bounded observe→propose→act loop toward ``goal``."""
    goal = (goal or "").strip()
    if not goal:
        return RunResult(
            status=TERMINAL_ERROR,
            goal=goal,
            steps=0,
            model=model or "",
            run_id=session.run_id,
            run_dir=str(session.run_dir),
            reason="empty goal",
        )

    if package:
        launched = session.launch(package)
        if not launched.get("ok"):
            return RunResult(
                status=TERMINAL_BLOCKED if launched.get("code") == "BLOCKED_BY_POLICY" else TERMINAL_ERROR,
                goal=goal,
                steps=0,
                model=model or "",
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                reason=str(launched.get("reason") or launched),
                history=[{"event": "launch", **launched}],
            )

    grounder = Grounder(model)
    history: list[dict[str, Any]] = []
    recent: list[str] = []
    last_summary = ""
    last_package = ""

    for step in range(1, max_steps + 1):
        obs = session.observe(detail="tree")
        last_summary = str(obs.get("summary") or "")
        last_package = str(obs.get("package") or "")
        safety = obs.get("safety") or {}
        entry: dict[str, Any] = {
            "step": step,
            "summary": last_summary,
            "package": last_package,
            "observe_safety": safety,
        }

        if safety.get("code") == "NEED_HUMAN" or safety.get("allow") is False:
            entry["stop"] = TERMINAL_HUMAN
            history.append(entry)
            session.log_event({"event": "android_run_stop", "status": TERMINAL_HUMAN, "step": step})
            return RunResult(
                status=TERMINAL_HUMAN,
                goal=goal,
                steps=step,
                model=grounder.model,
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                last_summary=last_summary,
                package=last_package,
                reason=str(safety.get("reason") or "payment/submit UI"),
                history=history,
            )

        image = Path(obs["screenshot_path"])
        proposed = grounder.propose(
            image, _instruction(goal, last_summary, step, max_steps)
        )
        entry["propose"] = {
            "ok": proposed.ok,
            "model": proposed.model,
            "action": proposed.action,
            "error": proposed.error,
        }
        if not proposed.ok or not proposed.action:
            entry["stop"] = TERMINAL_ERROR
            history.append(entry)
            return RunResult(
                status=TERMINAL_ERROR,
                goal=goal,
                steps=step,
                model=grounder.model,
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                last_summary=last_summary,
                package=last_package,
                reason=proposed.error or "propose failed",
                history=history,
            )

        action = proposed.action
        if action.get("action") == "terminate":
            status = (
                TERMINAL_OK
                if str(action.get("status") or "").lower() == "success"
                else TERMINAL_STUCK
            )
            entry["stop"] = status
            history.append(entry)
            session.log_event({"event": "android_run_stop", "status": status, "step": step})
            return RunResult(
                status=status,
                goal=goal,
                steps=step,
                model=grounder.model,
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                last_summary=last_summary,
                package=last_package,
                reason=f"terminate:{action.get('status')}",
                history=history,
            )

        w, h = session.last_size
        mapped = pixel_from_normalized(action, w, h) if w > 0 and h > 0 else dict(action)
        entry["mapped"] = {k: mapped.get(k) for k in ("action", "pixel", "pixel2", "text", "button") if k in mapped or k == "action"}
        fp = _action_fingerprint(action, mapped)
        recent.append(fp)
        if len(recent) >= stuck_repeat and len(set(recent[-stuck_repeat:])) == 1:
            entry["stop"] = TERMINAL_STUCK
            history.append(entry)
            return RunResult(
                status=TERMINAL_STUCK,
                goal=goal,
                steps=step,
                model=grounder.model,
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                last_summary=last_summary,
                package=last_package,
                reason=f"repeated action {fp}",
                history=history,
            )

        kind = str(action.get("action") or "")
        exec_result: dict[str, Any]
        if kind == "click" and "pixel" in mapped:
            x, y = mapped["pixel"]
            exec_result = session.tap(int(x), int(y), semantic_hint=goal[:120])
        elif kind == "swipe" and "pixel" in mapped and "pixel2" in mapped:
            x1, y1 = mapped["pixel"]
            x2, y2 = mapped["pixel2"]
            exec_result = session.swipe(int(x1), int(y1), int(x2), int(y2), semantic_hint=goal[:120])
        elif kind == "type":
            exec_result = session.type_text(str(action.get("text") or ""), semantic_hint=goal[:120])
        elif kind in {"system_button", "key"}:
            btn = str(action.get("button") or action.get("text") or "BACK")
            exec_result = session.press(btn)
        elif kind == "wait":
            import time

            time.sleep(min(max(float(action.get("time") or 1), 0.2), 5.0))
            exec_result = {"ok": True, "waited": True}
        else:
            exec_result = {"ok": False, "code": "UNSUPPORTED", "reason": f"kind={kind}"}

        entry["execution"] = exec_result
        history.append(entry)

        if not exec_result.get("ok"):
            code = str(exec_result.get("code") or "")
            if code == "BLOCKED_BY_POLICY":
                return RunResult(
                    status=TERMINAL_BLOCKED,
                    goal=goal,
                    steps=step,
                    model=grounder.model,
                    run_id=session.run_id,
                    run_dir=str(session.run_dir),
                    last_summary=last_summary,
                    package=last_package,
                    reason=str(exec_result.get("reason") or code),
                    history=history,
                )
            if code == "NEED_HUMAN":
                return RunResult(
                    status=TERMINAL_HUMAN,
                    goal=goal,
                    steps=step,
                    model=grounder.model,
                    run_id=session.run_id,
                    run_dir=str(session.run_dir),
                    last_summary=last_summary,
                    package=last_package,
                    reason=str(exec_result.get("reason") or code),
                    history=history,
                )
            return RunResult(
                status=TERMINAL_ERROR,
                goal=goal,
                steps=step,
                model=grounder.model,
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                last_summary=last_summary,
                package=last_package,
                reason=str(exec_result.get("reason") or exec_result),
                history=history,
            )

    session.log_event({"event": "android_run_stop", "status": TERMINAL_BUDGET, "steps": max_steps})
    return RunResult(
        status=TERMINAL_BUDGET,
        goal=goal,
        steps=max_steps,
        model=grounder.model,
        run_id=session.run_id,
        run_dir=str(session.run_dir),
        last_summary=last_summary,
        package=last_package,
        reason=f"exceeded max_steps={max_steps}",
        history=history,
    )
