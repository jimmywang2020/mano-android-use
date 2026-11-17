"""B-path: bounded android_run(goal) loop without LangGraph.

Reuses DeviceSession + Grounder + SafetyGateway. Host/CLI passes a goal; the
service observes, proposes, guards, and acts until a terminal status.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .apply_action import VIA_ANDROID_RUN, VIA_TREE_SHORTCUT, apply_action
from .grounder import Grounder, GrounderResult, pixel_from_normalized
from .session import DeviceSession
from .success_check import SuccessCheck, evaluate_success
from .tips import build_tips
from .trace_report import (
    build_step_span,
    cost_report_from_doc,
    trace_summary_from_doc,
    write_trace,
)
from .tree import compact_nodes

_DEFAULT_STUCK_SAME = 3
_QUOTED_LABEL_RE = re.compile(
    r"[「『\"“]([^」』\"”]{1,24})[」』\"”]"
)


TERMINAL_OK = "GOAL_REACHED"
TERMINAL_HUMAN = "NEED_HUMAN"
TERMINAL_BLOCKED = "BLOCKED_BY_POLICY"
TERMINAL_STUCK = "STUCK"
TERMINAL_BUDGET = "BUDGET_EXCEEDED"
TERMINAL_TIME_BUDGET = "TIME_BUDGET"
TERMINAL_ERROR = "ERROR"


def continue_hint_for_run(
    *,
    goal: str,
    package: str = "",
    last_summary: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Host guidance after TIME_BUDGET / incomplete MCP runs."""
    return {
        "action": "android_run",
        "suggestion": (
            "Resume with a short android_run from the current screen; "
            "do not cold-start unless context was lost; avoid L0 as the main loop."
        ),
        "goal": goal,
        "package": package or "",
        "last_summary": (last_summary or "")[:300],
        "recommended_max_steps": 8,
        "reason": status or "",
    }


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
    trace_summary: dict[str, Any] | None = None
    cost_report: dict[str, Any] | None = None
    continue_hint: dict[str, Any] | None = None

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
        if self.trace_summary is not None:
            out["trace_summary"] = self.trace_summary
        if self.cost_report is not None:
            out["cost_report"] = self.cost_report
        if self.continue_hint is not None:
            out["continue_hint"] = self.continue_hint
        return out


def _action_name(action: dict[str, Any] | None, proposed: GrounderResult | None = None) -> str:
    if action and action.get("action"):
        return str(action.get("action"))
    if proposed and proposed.action and proposed.action.get("action"):
        return str(proposed.action.get("action"))
    return ""


def _record_step_timing(
    session: DeviceSession,
    entry: dict[str, Any],
    *,
    step: int,
    model: str,
    observe_ms: int,
    grounder_ms: int = 0,
    act_ms: int = 0,
    proposed: GrounderResult | None = None,
    action: dict[str, Any] | None = None,
    via: str = VIA_ANDROID_RUN,
    vlm_skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    # Phase ms from perf_counter; tokens/calls from GrounderResult when present.
    span = build_step_span(
        step=step,
        model=model,
        observe_ms=observe_ms,
        grounder_ms=grounder_ms,
        act_ms=act_ms,
        prompt_tokens=int(proposed.prompt_tokens) if proposed else 0,
        completion_tokens=int(proposed.completion_tokens) if proposed else 0,
        grounder_calls=int(proposed.call_count) if proposed else 0,
        action=_action_name(action, proposed),
        via=via,
        vlm_skipped=vlm_skipped,
        skip_reason=skip_reason,
    )
    entry["timing"] = span
    if vlm_skipped:
        entry["vlm_skipped"] = True
        if skip_reason:
            entry["skip_reason"] = skip_reason
    session.log_event(dict(span))
    return span


def _action_fingerprint(action: dict[str, Any] | None, mapped: dict[str, Any] | None) -> str:
    if not action:
        return "none"
    kind = str(action.get("action") or "")
    if mapped and "pixel" in mapped:
        return f"{kind}:{mapped.get('pixel')}:{mapped.get('pixel2')}"
    return f"{kind}:{action.get('coordinate')}:{action.get('text')}:{action.get('button')}"


def _normalize_summary(summary: str) -> str:
    return re.sub(r"\s+", " ", (summary or "").strip())


def screen_signature(
    *,
    package: str,
    summary: str,
    xml: str = "",
) -> str:
    """Stable-ish screen id for unchanged detection (no image hash required)."""
    pkg = (package or "").strip()
    summ = _normalize_summary(summary)
    # Short / empty summaries (WebView) → fold in a coarse tree fingerprint.
    if len(summ) < 24 or "labels=[]" in summ:
        nodes = compact_nodes(xml or "", max_nodes=40)
        labels = []
        for n in nodes:
            lab = n.get("text") or n.get("desc") or n.get("resource_id")
            if lab:
                labels.append(str(lab)[:32])
            if len(labels) >= 12:
                break
        tree_fp = "|".join(labels)
        return f"{pkg}::{summ}::{tree_fp}"
    return f"{pkg}::{summ}"


def resolve_stuck_same_summary(value: int | None = None) -> int:
    """Default 3; ``0`` disables. Env ``MAU_STUCK_SAME_SUMMARY`` overrides when value is None."""
    if value is not None:
        return max(0, int(value))
    raw = os.getenv("MAU_STUCK_SAME_SUMMARY", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return _DEFAULT_STUCK_SAME


def extract_quoted_labels(goal: str, *, max_labels: int = 4) -> list[str]:
    """Pull short quoted labels from goal for tree-first find."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _QUOTED_LABEL_RE.finditer(goal or ""):
        lab = (m.group(1) or "").strip()
        if not lab or lab in seen:
            continue
        seen.add(lab)
        out.append(lab)
        if len(out) >= max_labels:
            break
    return out


def collect_tree_candidates(
    goal: str,
    tree_hints: list[str] | None = None,
) -> list[str]:
    cands: list[str] = []
    seen: set[str] = set()
    for raw in list(tree_hints or []) + extract_quoted_labels(goal):
        lab = str(raw or "").strip()
        if not lab or lab in seen:
            continue
        seen.add(lab)
        cands.append(lab)
    return cands


def try_tree_shortcut(
    session: DeviceSession,
    candidates: list[str],
) -> dict[str, Any] | None:
    """If exactly one find hit with a center, return tap target; else None."""
    if not candidates:
        return None
    for query in candidates:
        found = session.find(query, limit=5)
        hits = list(found.get("hits") or [])
        with_center = [h for h in hits if isinstance(h.get("center"), list) and len(h["center"]) >= 2]
        if len(with_center) == 1:
            c = with_center[0]["center"]
            return {
                "query": query,
                "x": int(c[0]),
                "y": int(c[1]),
                "hit": with_center[0],
            }
    return None


def _instruction(
    goal: str,
    summary: str,
    step: int,
    max_steps: int,
    *,
    success_check: SuccessCheck | None = None,
    check_feedback: str = "",
    goal_context: str = "",
) -> str:
    parts: list[str] = []
    if goal_context.strip():
        parts.append(goal_context.strip())
    parts.extend(
        [
            f"User goal: {goal}",
            f"Step {step}/{max_steps}. Current screen summary: {summary}",
            "Propose the single next UI action toward the goal. "
            "If the goal is already achieved, return "
            '{"action":"terminate","status":"success"}. '
            "Never pay, confirm payment, or submit an order.",
        ]
    )
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
    stuck_same_summary: int | None = None,
    success_check: SuccessCheck | dict[str, Any] | None = None,
    goal_context: str = "",
    wall_budget_ms: int = 0,
    tree_hints: list[str] | None = None,
) -> RunResult:
    """Run a bounded observe→propose→act loop toward ``goal``.

    Optional ``success_check`` (package / labels_any / labels_all) is an external
    verifier: early-stop when the screen matches; veto model ``terminate:success``
    when it does not.

    ``stuck_same_summary``: if > 0, skip VLM on unchanged screen (recover then
    STUCK). Default 3; ``0`` disables; ``None`` reads ``MAU_STUCK_SAME_SUMMARY``.

    ``tree_hints``: optional labels for tree-first find before VLM (also uses
    quoted labels inside ``goal``). Unique hit → tap with ``via=tree_shortcut``.

    ``wall_budget_ms``: if > 0, stop with TIME_BUDGET before the next observe once
    elapsed wall time reaches the budget (MCP soft timeout avoidance).
    """
    goal = (goal or "").strip()
    stuck_same_summary = resolve_stuck_same_summary(stuck_same_summary)
    tree_candidates = collect_tree_candidates(goal, tree_hints)
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
    prev_screen_sig = ""
    unchanged_streak = 0
    t_run0 = time.perf_counter()
    wall_budget_ms = max(0, int(wall_budget_ms or 0))

    def _result(
        status: str,
        *,
        steps: int,
        reason: str,
        verdict: dict[str, Any] | None = None,
        with_continue_hint: bool = False,
    ) -> RunResult:
        trace_doc = write_trace(
            session.run_dir,
            run_id=session.run_id,
            goal=goal,
            status=status,
            model=grounder.model,
            history=history,
        )
        hint = None
        if with_continue_hint or status == TERMINAL_TIME_BUDGET:
            hint = continue_hint_for_run(
                goal=goal,
                package=last_package,
                last_summary=last_summary,
                status=status,
            )
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
            trace_summary=trace_summary_from_doc(trace_doc),
            cost_report=cost_report_from_doc(trace_doc),
            continue_hint=hint,
        )

    for step in range(1, max_steps + 1):
        if wall_budget_ms > 0:
            elapsed_ms = max(0, int((time.perf_counter() - t_run0) * 1000))
            if elapsed_ms >= wall_budget_ms:
                session.log_event(
                    {
                        "event": "android_run_stop",
                        "status": TERMINAL_TIME_BUDGET,
                        "step": max(0, step - 1),
                        "via": VIA_ANDROID_RUN,
                        "reason": "wall_budget_ms",
                        "wall_budget_ms": wall_budget_ms,
                        "elapsed_ms": elapsed_ms,
                    }
                )
                return _result(
                    TERMINAL_TIME_BUDGET,
                    steps=max(0, step - 1),
                    reason=f"wall_budget_ms={wall_budget_ms} elapsed_ms={elapsed_ms}",
                    with_continue_hint=True,
                )

        t_obs0 = time.perf_counter()
        obs = session.observe(detail="tree")
        observe_ms = max(0, int((time.perf_counter() - t_obs0) * 1000))
        last_summary = str(obs.get("summary") or "")
        last_package = str(obs.get("package") or "")
        safety = obs.get("safety") or {}
        sig = screen_signature(
            package=last_package,
            summary=last_summary,
            xml=session.last_xml or "",
        )
        entry: dict[str, Any] = {
            "step": step,
            "summary": last_summary,
            "package": last_package,
            "observe_safety": safety,
            "screen_sig": sig,
        }

        if stuck_same_summary > 0 and prev_screen_sig and sig == prev_screen_sig:
            unchanged_streak += 1
            entry["unchanged_streak"] = unchanged_streak
            if unchanged_streak >= stuck_same_summary:
                _record_step_timing(
                    session,
                    entry,
                    step=step,
                    model=grounder.model,
                    observe_ms=observe_ms,
                    vlm_skipped=True,
                    skip_reason="unchanged_stuck",
                    via=VIA_ANDROID_RUN,
                )
                entry["stop"] = TERMINAL_STUCK
                history.append(entry)
                session.log_event(
                    {
                        "event": "android_run_stop",
                        "status": TERMINAL_STUCK,
                        "step": step,
                        "via": VIA_ANDROID_RUN,
                        "reason": "unchanged_screen",
                        "unchanged_streak": unchanged_streak,
                    }
                )
                return _result(
                    TERMINAL_STUCK,
                    steps=step,
                    reason=f"unchanged screen x{unchanged_streak}",
                    with_continue_hint=True,
                )
            # Graded recover: first unchanged → BACK; later → short wait. No VLM.
            t_act0 = time.perf_counter()
            if unchanged_streak == 1:
                exec_result = session.press("BACK", via=VIA_ANDROID_RUN)
                recover_action = "system_button"
                skip_reason = "unchanged_recover"
            else:
                time.sleep(0.4)
                exec_result = {"ok": True, "waited": True, "via": VIA_ANDROID_RUN}
                recover_action = "wait"
                skip_reason = "unchanged_wait"
            act_ms = max(0, int((time.perf_counter() - t_act0) * 1000))
            entry["execution"] = exec_result
            entry["unchanged_recover"] = skip_reason
            session.log_event(
                {
                    "event": "unchanged_recover",
                    "step": step,
                    "streak": unchanged_streak,
                    "action": recover_action,
                    "skip_reason": skip_reason,
                }
            )
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
                act_ms=act_ms,
                action={"action": recover_action},
                via="unchanged_recover",
                vlm_skipped=True,
                skip_reason=skip_reason,
            )
            history.append(entry)
            # Keep prev_screen_sig so next observe can extend the streak.
            continue
        else:
            unchanged_streak = 0
            prev_screen_sig = sig

        if safety.get("code") == "NEED_HUMAN" or safety.get("allow") is False:
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
            )
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
                _record_step_timing(
                    session,
                    entry,
                    step=step,
                    model=grounder.model,
                    observe_ms=observe_ms,
                    vlm_skipped=True,
                    skip_reason="success_check",
                )
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

        # Tree-first: unique find hit → tap without VLM.
        tree_hit = try_tree_shortcut(session, tree_candidates)
        if tree_hit:
            t_act0 = time.perf_counter()
            exec_result = session.tap(
                int(tree_hit["x"]),
                int(tree_hit["y"]),
                semantic_hint=str(tree_hit.get("query") or goal)[:120],
                via=VIA_TREE_SHORTCUT,
            )
            act_ms = max(0, int((time.perf_counter() - t_act0) * 1000))
            entry["tree_shortcut"] = {
                "query": tree_hit.get("query"),
                "xy": [tree_hit["x"], tree_hit["y"]],
            }
            entry["execution"] = exec_result
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
                act_ms=act_ms,
                action={"action": "click"},
                via=VIA_TREE_SHORTCUT,
                vlm_skipped=True,
                skip_reason="tree_shortcut",
            )
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
            # Drop the used hint so we do not re-tap the same label forever.
            used = str(tree_hit.get("query") or "")
            tree_candidates = [c for c in tree_candidates if c != used]
            continue

        image = Path(obs["screenshot_path"])
        t_g0 = time.perf_counter()
        proposed = grounder.propose(
            image,
            _instruction(
                goal,
                last_summary,
                step,
                max_steps,
                success_check=success_check if isinstance(success_check, SuccessCheck) else None,
                check_feedback=check_feedback,
                goal_context=goal_context,
            ),
        )
        grounder_ms = max(0, int((time.perf_counter() - t_g0) * 1000))
        check_feedback = ""
        entry["propose"] = {
            "ok": proposed.ok,
            "model": proposed.model,
            "action": proposed.action,
            "error": proposed.error,
            "latency_ms": proposed.latency_ms,
            "prompt_tokens": proposed.prompt_tokens,
            "completion_tokens": proposed.completion_tokens,
            "call_count": proposed.call_count,
        }
        if not proposed.ok or not proposed.action:
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
                grounder_ms=grounder_ms,
                proposed=proposed,
            )
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
                    _record_step_timing(
                        session,
                        entry,
                        step=step,
                        model=grounder.model,
                        observe_ms=observe_ms,
                        grounder_ms=grounder_ms,
                        proposed=proposed,
                        action=action,
                    )
                    history.append(entry)
                    continue
                _record_step_timing(
                    session,
                    entry,
                    step=step,
                    model=grounder.model,
                    observe_ms=observe_ms,
                    grounder_ms=grounder_ms,
                    proposed=proposed,
                    action=action,
                )
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
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
                grounder_ms=grounder_ms,
                proposed=proposed,
                action=action,
            )
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
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
                grounder_ms=grounder_ms,
                proposed=proposed,
                action=action,
            )
            entry["stop"] = TERMINAL_STUCK
            history.append(entry)
            return _result(
                TERMINAL_STUCK,
                steps=step,
                reason=f"repeated action {fp}",
            )

        t_act0 = time.perf_counter()
        exec_result = apply_action(
            session,
            action,
            mapped,
            semantic_hint=goal[:120],
            via=VIA_ANDROID_RUN,
        )
        act_ms = max(0, int((time.perf_counter() - t_act0) * 1000))

        entry["execution"] = exec_result
        _record_step_timing(
            session,
            entry,
            step=step,
            model=grounder.model,
            observe_ms=observe_ms,
            grounder_ms=grounder_ms,
            act_ms=act_ms,
            proposed=proposed,
            action=action,
        )
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
