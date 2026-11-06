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
from .success_check import SuccessCheck, evaluate_success
from .tips import build_tips


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
    tips: list[str] = field(default_factory=list)
    screen: dict[str, Any] | None = None
    success_check: dict[str, Any] | None = None
    success_verdict: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
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
        if self.tips:
            out["tips"] = self.tips
        if self.screen is not None:
            out["screen"] = self.screen
        if self.success_check is not None:
            out["success_check"] = self.success_check
        if self.success_verdict is not None:
            out["success_verdict"] = self.success_verdict
        return out


def _action_fingerprint(action: dict[str, Any] | None, mapped: dict[str, Any] | None) -> str:
    if not action:
        return "none"
    kind = str(action.get("action") or "")
    if mapped and "pixel" in mapped:
        return f"{kind}:{mapped.get('pixel')}:{mapped.get('pixel2')}"
    return f"{kind}:{action.get('coordinate')}:{action.get('text')}:{action.get('button')}"


def _instruction(
    goal: str,
    summary: str,
    step: int,
    max_steps: int,
    *,
    success_check: SuccessCheck | None = None,
    check_feedback: str = "",
) -> str:
    parts = [
        f"User goal: {goal}",
        f"Step {step}/{max_steps}. Current screen summary: {summary}",
        "Propose the single next UI action toward the goal. "
        "If the goal is already achieved, return "
        '{"action":"terminate","status":"success"}. '
        "Never pay, confirm payment, or submit an order.",
    ]
    if success_check and not success_check.is_empty():
        parts.append(
            "External success_check (must hold before success is accepted): "
            + str(success_check.to_dict())
        )
    if check_feedback:
        parts.append(f"Previous terminate rejected: {check_feedback}. Continue toward the goal.")
    return "\n".join(parts)


def android_run(
    session: DeviceSession,
    goal: str,
    *,
    max_steps: int = 25,
    model: str | None = None,
    package: str | None = None,
    stuck_repeat: int = 3,
    success_check: SuccessCheck | dict[str, Any] | None = None,
) -> RunResult:
    """Run a bounded observe→propose→act loop toward ``goal``.

    Optional ``success_check`` (package / labels_any / labels_all) is an external
    verifier: early-stop when the screen matches; veto model ``terminate:success``
    when it does not.
    """
    goal = (goal or "").strip()
    if isinstance(success_check, dict):
        success_check = SuccessCheck.from_mapping(success_check)
    check_dict = success_check.to_dict() if isinstance(success_check, SuccessCheck) else None

    if not goal:
        return RunResult(
            status=TERMINAL_ERROR,
            goal=goal,
            steps=0,
            model=model or "",
            run_id=session.run_id,
            run_dir=str(session.run_dir),
            reason="empty goal",
            tips=build_tips(include_playbook=True),
            success_check=check_dict,
        )

    # Consumer preflight: try one wake; still off → NEED_HUMAN (no Core change).
    screen = session.ensure_awake(auto_wake=True)
    if not screen.get("awake"):
        tips = build_tips(screen=screen, include_playbook=True)
        session.log_event(
            {"event": "android_run_stop", "status": TERMINAL_HUMAN, "reason": "screen_off"}
        )
        return RunResult(
            status=TERMINAL_HUMAN,
            goal=goal,
            steps=0,
            model=model or "",
            run_id=session.run_id,
            run_dir=str(session.run_dir),
            reason="screen off or not awake after KEYCODE_WAKEUP; unlock device and retry",
            tips=tips,
            screen=screen,
            history=[{"event": "screen_preflight", **screen}],
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
    check_feedback = ""

    def _result(
        status: str,
        *,
        steps: int,
        reason: str,
        verdict: dict[str, Any] | None = None,
    ) -> RunResult:
        return RunResult(
            status=status,
            goal=goal,
            steps=steps,
            model=grounder.model,
            run_id=session.run_id,
            run_dir=str(session.run_dir),
            last_summary=last_summary,
            package=last_package,
            reason=reason,
            history=history,
            success_check=check_dict,
            success_verdict=verdict,
        )

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
            return _result(
                TERMINAL_HUMAN,
                steps=step,
                reason=str(safety.get("reason") or "payment/submit UI"),
            )

        # External verifier: screen already matches → success without model terminate.
        if success_check and not success_check.is_empty():
            verdict = evaluate_success(
                success_check,
                package=last_package,
                summary=last_summary,
                xml=session.last_xml or "",
            )
            entry["success_check"] = verdict.to_dict()
            if verdict.ok:
                entry["stop"] = TERMINAL_OK
                history.append(entry)
                session.log_event(
                    {"event": "android_run_stop", "status": TERMINAL_OK, "step": step, "via": "success_check"}
                )
                return _result(
                    TERMINAL_OK,
                    steps=step,
                    reason="success_check satisfied",
                    verdict=verdict.to_dict(),
                )

        image = Path(obs["screenshot_path"])
        proposed = grounder.propose(
            image,
            _instruction(
                goal,
                last_summary,
                step,
                max_steps,
                success_check=success_check if isinstance(success_check, SuccessCheck) else None,
                check_feedback=check_feedback,
            ),
        )
        check_feedback = ""
        entry["propose"] = {
            "ok": proposed.ok,
            "model": proposed.model,
            "action": proposed.action,
            "error": proposed.error,
        }
        if not proposed.ok or not proposed.action:
            entry["stop"] = TERMINAL_ERROR
            history.append(entry)
            return _result(
                TERMINAL_ERROR,
                steps=step,
                reason=proposed.error or "propose failed",
            )

        action = proposed.action
        if action.get("action") == "terminate":
            want_ok = str(action.get("status") or "").lower() == "success"
            if want_ok and success_check and not success_check.is_empty():
                verdict = evaluate_success(
                    success_check,
                    package=last_package,
                    summary=last_summary,
                    xml=session.last_xml or "",
                )
                entry["success_check"] = verdict.to_dict()
                if not verdict.ok:
                    # Veto false success; keep looping with feedback.
                    check_feedback = "; ".join(verdict.reasons) or "success_check failed"
                    entry["terminate_vetoed"] = True
                    history.append(entry)
                    continue
                entry["stop"] = TERMINAL_OK
                history.append(entry)
                session.log_event({"event": "android_run_stop", "status": TERMINAL_OK, "step": step})
                return _result(
                    TERMINAL_OK,
                    steps=step,
                    reason="terminate:success+success_check",
                    verdict=verdict.to_dict(),
                )
            status = TERMINAL_OK if want_ok else TERMINAL_STUCK
            entry["stop"] = status
            history.append(entry)
            session.log_event({"event": "android_run_stop", "status": status, "step": step})
            return _result(
                status,
                steps=step,
                reason=f"terminate:{action.get('status')}",
            )

        w, h = session.last_size
        mapped = pixel_from_normalized(action, w, h) if w > 0 and h > 0 else dict(action)
        entry["mapped"] = {k: mapped.get(k) for k in ("action", "pixel", "pixel2", "text", "button") if k in mapped or k == "action"}
        fp = _action_fingerprint(action, mapped)
        recent.append(fp)
        if len(recent) >= stuck_repeat and len(set(recent[-stuck_repeat:])) == 1:
            entry["stop"] = TERMINAL_STUCK
            history.append(entry)
            return _result(
                TERMINAL_STUCK,
                steps=step,
                reason=f"repeated action {fp}",
            )

        kind = str(action.get("action") or "")
        # gui-plus sometimes emits system_button_press + button_name instead of
        # system_button + button (seen on ColorOS / phone runs).
        if kind in {"system_button_press", "press", "keyevent"}:
            kind = "system_button"
            if "button" not in action and action.get("button_name"):
                action = {**action, "button": action.get("button_name")}
                mapped = {**mapped, "button": action.get("button_name")}
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
            btn = str(
                action.get("button")
                or action.get("button_name")
                or action.get("text")
                or "BACK"
            )
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
                return _result(
                    TERMINAL_BLOCKED,
                    steps=step,
                    reason=str(exec_result.get("reason") or code),
                )
            if code == "NEED_HUMAN":
                return _result(
                    TERMINAL_HUMAN,
                    steps=step,
                    reason=str(exec_result.get("reason") or code),
                )
            return _result(
                TERMINAL_ERROR,
                steps=step,
                reason=str(exec_result.get("reason") or exec_result),
            )

    session.log_event({"event": "android_run_stop", "status": TERMINAL_BUDGET, "steps": max_steps})
    final_verdict = None
    if success_check and not success_check.is_empty():
        final_verdict = evaluate_success(
            success_check,
            package=last_package,
            summary=last_summary,
            xml=session.last_xml or "",
        ).to_dict()
    return _result(
        TERMINAL_BUDGET,
        steps=max_steps,
        reason=f"exceeded max_steps={max_steps}",
        verdict=final_verdict,
    )
