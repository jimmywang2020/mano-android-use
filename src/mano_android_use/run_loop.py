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
from .success_check import SuccessCheck, evaluate_success, progress_from_verdict
from .tips import build_tips
from .trace_report import (
    build_step_span,
    cost_report_from_history,
    trace_summary_from_doc,
    write_trace,
)
from .tree import compact_nodes

_DEFAULT_STUCK_SAME = 3
_SPARSE_TREE_MIN_NODES = 3
# After a successful type/click/swipe, skip unchanged→BACK for this many
# following steps so IME / sheet animations can settle without undoing the act.
_ACT_GRACE_STEPS = 2
_ACT_GRACE_KINDS = frozenset({"type", "click", "swipe"})
_QUOTED_LABEL_RE = re.compile(
    r"[「『\"“]([^」』\"”]{1,24})[」』\"”]"
)


def tree_is_sparse(obs: dict[str, Any], *, min_nodes: int = _SPARSE_TREE_MIN_NODES) -> bool:
    """True when a11y tree is too thin to gate on (typical WebView / empty dump)."""
    nodes = obs.get("tree_compact")
    if not isinstance(nodes, list):
        return True
    if len(nodes) < min_nodes:
        return True
    labeled = 0
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if str(n.get("text") or n.get("desc") or "").strip():
            labeled += 1
    return labeled < 1


def _merge_observe_breakdown(
    acc: dict[str, Any] | None,
    obs: dict[str, Any],
) -> dict[str, Any]:
    """Accumulate Core observe breakdown across tree + upgrade captures."""
    out = dict(acc or {})
    bd = obs.get("observe_breakdown") if isinstance(obs.get("observe_breakdown"), dict) else {}
    mode = str(obs.get("capture_mode") or bd.get("capture_mode") or "")
    modes = list(out.get("modes") or [])
    if mode:
        modes.append(mode)
    out["modes"] = modes
    out["screenshot_ms"] = int(out.get("screenshot_ms") or 0) + int(bd.get("screenshot_ms") or 0)
    out["xml_ms"] = int(out.get("xml_ms") or 0) + int(bd.get("xml_ms") or 0)
    out["capture_attempt"] = int(out.get("capture_attempt") or 0) + int(
        bd.get("capture_attempt") or 0
    )
    out["final_mode"] = mode or str(out.get("final_mode") or "")
    backend = str(obs.get("observe_backend") or bd.get("observe_backend") or "")
    if backend:
        out["observe_backend"] = backend
        out["final_backend"] = backend
        backends = list(out.get("backends") or [])
        backends.append(backend)
        out["backends"] = backends
    return out


def ensure_observation_for_grounder(
    session: DeviceSession,
    obs: dict[str, Any],
) -> tuple[dict[str, Any], int, str]:
    """Upgrade tree-only observe to one full capture before VLM.

    Uses a single ``full`` (screenshot+XML) instead of tree-then-shot, so the
    Grounder pays one ADB window rather than two.
    """
    mode = str(obs.get("capture_mode") or "")
    shot = str(obs.get("screenshot_path") or "")
    if mode == "full" and shot and Path(shot).is_file():
        return obs, 0, ""
    t0 = time.perf_counter()
    upgraded = session.observe(detail="both", bump_step=False)
    reason = "full_sparse_tree" if tree_is_sparse(obs) else "full_for_vlm"
    ms = max(0, int((time.perf_counter() - t0) * 1000))
    return upgraded, ms, reason


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
    progress: dict[str, Any] | None = None,
    screen_digest: dict[str, Any] | None = None,
    tree_hints: list[str] | None = None,
    success_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Host ResumeSpec — emitted on every android_run terminal status.

    Keeps legacy keys (``action``, ``goal``, …) and adds structured ``do`` /
    ``dont`` / ``progress``. On ``GOAL_REACHED``, ``next_actor=done`` (Host may
    still read progress/digest); otherwise Host fills ``do.*`` and honors dont[].
    """
    digest = screen_digest if isinstance(screen_digest, dict) else {}
    prog = dict(progress or {})
    hints = [str(h).strip() for h in (tree_hints or []) if str(h).strip()]
    check = success_check if isinstance(success_check, dict) else None
    done = status == TERMINAL_OK
    if done:
        suggestion = (
            "Goal reached. Carry progress/screen_digest in Host TaskState; "
            "do not HOME/force-stop. Optional follow-up: short android_run with "
            "omit_package= and cold_start=false only if refining the same screen."
        )
        next_actor = "done"
    else:
        suggestion = (
            "Resume with a short android_run from the current screen; "
            "omit package= (or cold_start=false) so mau does not force-stop; "
            "avoid L0 as the main loop. Prefer resume.do fields; honor dont[]."
        )
        next_actor = "host"
    return {
        # Legacy keys (compat)
        "action": "android_run",
        "suggestion": suggestion,
        "goal": goal,
        "package": package or "",
        "last_summary": (last_summary or "")[:300],
        "recommended_max_steps": 8,
        "cold_start": False,
        "reason": status or "",
        # ResumeSpec (structured)
        "next_actor": next_actor,
        "do": {
            "tool": "android_run",
            "goal": goal,
            "omit_package": True,
            "cold_start": False,
            "max_steps": 8,
            "tree_hints": hints,
            "success_check": check or {},
        },
        "dont": [
            "HOME",
            "force_stop",
            "launch_app",
            "rewrite_goal_from_scratch",
            "propose_action_loop",
        ],
        "progress": prog,
        "screen_digest": digest,
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
    progress: dict[str, Any] | None = None
    screen_digest: dict[str, Any] | None = None

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
            # Alias for Host TaskState consumers
            out["resume"] = self.continue_hint
        if self.progress:
            out["progress"] = self.progress
        if self.screen_digest is not None:
            out["screen_digest"] = self.screen_digest
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
    observe_breakdown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Phase ms from perf_counter; tokens/calls from GrounderResult when present.
    bd = observe_breakdown if isinstance(observe_breakdown, dict) else entry.get("observe_breakdown")
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
        observe_breakdown=bd if isinstance(bd, dict) else None,
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
    """Stable-ish screen id for unchanged detection (no image hash required).

    Always folds in a systemui-filtered foreground tree fingerprint so ColorOS
    status-bar noise cannot pin the signature across real UI changes.
    """
    from .tree import screen_digest_labels

    pkg = (package or "").strip()
    summ = _normalize_summary(summary)
    labels = screen_digest_labels(xml or "", package=pkg or None, max_labels=16, max_nodes=80)
    tree_fp = "|".join(labels) if labels else ""
    # Prefer digest when summary is empty/thin; always append fingerprint when present.
    if tree_fp:
        return f"{pkg}::{summ}::{tree_fp}"
    return f"{pkg}::{summ}"


def screen_digest_dict(
    *,
    package: str,
    summary: str,
    xml: str = "",
    screenshot_path: str = "",
    xml_path: str = "",
) -> dict[str, Any]:
    """Host-facing digest: filtered labels + signature + evidence paths (no full XML)."""
    from .tree import screen_digest_labels

    pkg = (package or "").strip()
    labels = screen_digest_labels(xml or "", package=pkg or None, max_labels=24, max_nodes=120)
    out: dict[str, Any] = {
        "package": pkg,
        "labels": labels,
        "summary": _normalize_summary(summary)[:240],
        "signature": screen_signature(package=pkg, summary=summary, xml=xml),
    }
    refs: dict[str, str] = {}
    if screenshot_path:
        refs["screenshot"] = str(screenshot_path)
    if xml_path:
        refs["xml"] = str(xml_path)
    if refs:
        out["evidence_refs"] = refs
    return out


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
    progress: dict[str, Any] | None = None,
    digest_labels: list[str] | None = None,
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
    # Short RunMemory view for Grounder (format on demand; keep token-light).
    prog = {k: v for k, v in (progress or {}).items() if v}
    if prog:
        bits = [f"{k}" for k in list(prog.keys())[:12]]
        parts.append("Known progress bits (do not undo): " + ", ".join(bits) + ".")
    labels = [str(x).strip() for x in (digest_labels or []) if str(x).strip()]
    if labels:
        parts.append("Screen digest labels: " + ", ".join(labels[:16]) + ".")
    if prog.get("fare_seen") or prog.get("cart_seen"):
        parts.append(
            "Progress hold: fare/cart already seen — do not press BACK/HOME; "
            "prefer terminate:success if the quote/cart UI is visible."
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
    cold_start: bool = False,
    new_run: bool = True,
    initial_progress: dict[str, Any] | None = None,
) -> RunResult:
    """Run a bounded observe→propose→act loop toward ``goal``.

    Optional ``success_check`` (package / labels_any / labels_all) is an external
    verifier: early-stop when the screen matches; veto model ``terminate:success``
    when it does not.

    ``stuck_same_summary``: if > 0, skip VLM on unchanged screen (recover then
    STUCK). Default 3; ``0`` disables; ``None`` reads ``MAU_STUCK_SAME_SUMMARY``.
    After a successful ``type`` / ``click`` / ``swipe``, the next
    ``_ACT_GRACE_STEPS`` steps skip unchanged→BACK so IME / sheets can settle.

    ``tree_hints``: optional labels for tree-first find before VLM (also uses
    quoted labels inside ``goal``). Unique hit → tap with ``via=tree_shortcut``.

    ``wall_budget_ms``: if > 0, stop with TIME_BUDGET before the next observe once
    elapsed wall time reaches the budget (MCP soft timeout avoidance).

    ``package`` + ``cold_start=False`` (default): warm ensure (skip force-stop when
    already foreground). Pass ``cold_start=True`` only for a true relaunch.

    ``new_run``: when True (default), rotate to a fresh ``run_id``/``run_dir`` so
    Host ``cost_report`` is scoped to this call. Plan stages pass False.

    ``initial_progress``: OR-seed from prior plan stage / Host TaskState (merge-only).
    """
    if new_run and hasattr(session, "begin_run"):
        session.begin_run()
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
        launched = session.launch(package, cold=bool(cold_start))
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
    act_grace_remaining = 0
    # Grace arms at most once per screen signature so repeated no-op clicks
    # cannot refresh the window forever and block unchanged→STUCK.
    act_grace_sig = ""
    progress: dict[str, Any] = {}
    last_digest: dict[str, Any] = {}
    t_run0 = time.perf_counter()
    wall_budget_ms = max(0, int(wall_budget_ms or 0))

    def _merge_progress(extra: dict[str, Any] | None) -> None:
        for k, v in (extra or {}).items():
            if v:
                progress[k] = v

    _merge_progress(initial_progress)

    def _result(
        status: str,
        *,
        steps: int,
        reason: str,
        verdict: dict[str, Any] | None = None,
        with_continue_hint: bool = False,
    ) -> RunResult:
        del with_continue_hint  # ResumeSpec is always attached now.
        trace_doc = write_trace(
            session.run_dir,
            run_id=session.run_id,
            goal=goal,
            status=status,
            model=grounder.model,
            history=history,
        )
        hint = continue_hint_for_run(
            goal=goal,
            package=last_package,
            last_summary=last_summary,
            status=status,
            progress=progress,
            screen_digest=last_digest,
            tree_hints=tree_candidates,
            success_check=check_dict,
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
            # Host cost is scoped to this android_run history (not prior MCP
            # tasks that may share a long-lived DeviceSession before begin_run).
            trace_summary=trace_summary_from_doc(trace_doc),
            cost_report=cost_report_from_history(history),
            continue_hint=hint,
            progress=dict(progress) if progress else None,
            screen_digest=dict(last_digest) if last_digest else None,
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
        try:
            # Every step: one full capture (screenshot+XML). Tree gate / VLM skip
            # still apply on the same observe — no tree→full double tax.
            obs = session.observe(detail="both")
        except Exception as exc:  # noqa: BLE001 — fail fast; do not burn MCP wall
            observe_ms = max(0, int((time.perf_counter() - t_obs0) * 1000))
            session.log_event(
                {
                    "event": "android_run_stop",
                    "status": TERMINAL_ERROR,
                    "step": step,
                    "via": VIA_ANDROID_RUN,
                    "reason": "observe_failed",
                    "error": str(exc)[:300],
                    "observe_ms": observe_ms,
                }
            )
            return _result(
                TERMINAL_ERROR,
                steps=max(0, step - 1),
                reason=f"observe failed: {exc}",
                with_continue_hint=True,
            )
        observe_ms = max(0, int((time.perf_counter() - t_obs0) * 1000))
        observe_bd = _merge_observe_breakdown(None, obs)
        last_summary = str(obs.get("summary") or "")
        last_package = str(obs.get("package") or "")
        safety = obs.get("safety") or {}
        last_digest = screen_digest_dict(
            package=last_package,
            summary=last_summary,
            xml=session.last_xml or "",
            screenshot_path=str(obs.get("screenshot_path") or ""),
            xml_path=str(obs.get("xml_path") or ""),
        )
        sig = str(last_digest.get("signature") or "")
        entry: dict[str, Any] = {
            "step": step,
            "summary": last_summary,
            "package": last_package,
            "observe_safety": safety,
            "screen_sig": sig,
            "screen_digest": last_digest,
            "observe_breakdown": observe_bd,
            "capture_mode": obs.get("capture_mode") or "full",
        }

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

        # External verifier BEFORE unchanged recover — so fare/cart screens are
        # not undone by a false-identical dirty signature (U2/ColorOS).
        if success_check and not success_check.is_empty():
            verdict = evaluate_success(
                success_check,
                package=last_package,
                summary=last_summary,
                xml=session.last_xml or "",
            )
            entry["success_check"] = verdict.to_dict()
            _merge_progress(progress_from_verdict(success_check, verdict))
            entry["progress"] = dict(progress)
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

        if stuck_same_summary > 0 and prev_screen_sig and sig == prev_screen_sig:
            if act_grace_remaining > 0:
                # Recent type/click/swipe: do not BACK; let tree_shortcut / VLM continue.
                act_grace_remaining -= 1
                entry["act_grace"] = True
                entry["act_grace_remaining"] = act_grace_remaining
                # Keep type_grace_* aliases for older journals / tests.
                entry["type_grace"] = True
                entry["type_grace_remaining"] = act_grace_remaining
                unchanged_streak = 0
                prev_screen_sig = sig
                session.log_event(
                    {
                        "event": "act_grace_skip_unchanged",
                        "step": step,
                        "act_grace_remaining": act_grace_remaining,
                    }
                )
            elif progress.get("fare_seen") or progress.get("cart_seen"):
                # Saw fare/cart labels but full success_check not yet ok — hold
                # the screen (no BACK) and hand Host a ResumeSpec with progress.
                _record_step_timing(
                    session,
                    entry,
                    step=step,
                    model=grounder.model,
                    observe_ms=observe_ms,
                    vlm_skipped=True,
                    skip_reason="progress_hold",
                    via=VIA_ANDROID_RUN,
                )
                entry["stop"] = TERMINAL_STUCK
                history.append(entry)
                session.log_event(
                    {
                        "event": "android_run_stop",
                        "status": TERMINAL_STUCK,
                        "step": step,
                        "via": "progress_hold",
                        "progress": dict(progress),
                    }
                )
                return _result(
                    TERMINAL_STUCK,
                    steps=step,
                    reason="progress hold (skip unchanged BACK; Host resume)",
                    with_continue_hint=True,
                )
            else:
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

        # Tree-first: unique find hit → tap without VLM.
        tree_hit = try_tree_shortcut(session, tree_candidates)
        if tree_hit:
            t_act0 = time.perf_counter()
            exec_result = session.tap(
                int(tree_hit["x"]),
                int(tree_hit["y"]),
                semantic_hint=str(tree_hit.get("query") or goal),
                via=VIA_TREE_SHORTCUT,
            )
            act_ms = max(0, int((time.perf_counter() - t_act0) * 1000))
            entry["tree_shortcut"] = {
                "query": tree_hit.get("query"),
                "xy": [tree_hit["x"], tree_hit["y"]],
            }
            entry["execution"] = exec_result
            if exec_result.get("ok") and act_grace_sig != sig:
                act_grace_remaining = _ACT_GRACE_STEPS
                act_grace_sig = sig
                entry["act_grace_armed"] = act_grace_remaining
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

        # Fallback if full observe somehow lacked a PNG (should be no-op normally).
        obs, upgrade_ms, upgrade_reason = ensure_observation_for_grounder(session, obs)
        if upgrade_reason:
            observe_ms += upgrade_ms
            observe_bd = _merge_observe_breakdown(observe_bd, obs)
            entry["observe_breakdown"] = observe_bd
            entry["observe_upgrade"] = upgrade_reason
            entry["capture_mode"] = obs.get("capture_mode") or entry.get("capture_mode")
            last_summary = str(obs.get("summary") or last_summary)
            last_package = str(obs.get("package") or last_package)
            entry["summary"] = last_summary
            entry["package"] = last_package
        image = Path(str(obs.get("screenshot_path") or ""))
        if not image.is_file():
            _record_step_timing(
                session,
                entry,
                step=step,
                model=grounder.model,
                observe_ms=observe_ms,
            )
            entry["stop"] = TERMINAL_ERROR
            history.append(entry)
            return _result(
                TERMINAL_ERROR,
                steps=step,
                reason="observe upgrade produced no screenshot for grounder",
            )
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
                progress=progress,
                digest_labels=list(last_digest.get("labels") or []),
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
                _merge_progress(progress_from_verdict(success_check, verdict))
                entry["progress"] = dict(progress)
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
            semantic_hint=goal,
            via=VIA_ANDROID_RUN,
        )
        act_ms = max(0, int((time.perf_counter() - t_act0) * 1000))

        entry["execution"] = exec_result
        kind = str(action.get("action") or "")
        if exec_result.get("ok") and kind in _ACT_GRACE_KINDS and act_grace_sig != sig:
            act_grace_remaining = _ACT_GRACE_STEPS
            act_grace_sig = sig
            entry["act_grace_armed"] = act_grace_remaining
            if kind == "type":
                entry["type_grace_armed"] = act_grace_remaining
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
            # Malformed VLM actions (e.g. click without coordinates) used to
            # abort the whole stage as ERROR; skip and let the next observe retry.
            if code == "UNSUPPORTED" or exec_result.get("retryable"):
                reason = str(exec_result.get("reason") or code or "unsupported action")
                check_feedback = f"previous action rejected: {reason}"
                entry["action_skipped"] = True
                entry["skip_reason"] = "unsupported_action"
                session.log_event(
                    {
                        "event": "action_skipped",
                        "step": step,
                        "reason": reason,
                        "code": code,
                    }
                )
                continue
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
