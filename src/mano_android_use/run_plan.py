"""Staged android_run: generic multi-step plans with per-stage success_check.

App-agnostic: Ctrip / Meituan / others differ only in plan JSON (goals + checks),
not in runner code. Host may also call android_run three times manually.

Minimal PlanState is passed between stages so later stages continue from prior
progress instead of re-opening the app / redoing completed work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .run_loop import (
    TERMINAL_OK,
    TERMINAL_TIME_BUDGET,
    RunResult,
    android_run,
    continue_hint_for_run,
)
from .session import DeviceSession
from .success_check import SuccessCheck
from .trace_report import plan_cost_report


def _or_merge_progress(
    base: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(base or {})
    for k, v in (extra or {}).items():
        if v:
            out[k] = v
    return out


@dataclass
class PlanState:
    """Thin cross-stage memory (LangGraph-style state, without LangGraph)."""

    completed_stage_ids: list[str] = field(default_factory=list)
    last_summary: str = ""
    last_package: str = ""
    last_reason: str = ""
    progress: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_stage_ids": list(self.completed_stage_ids),
            "last_summary": self.last_summary,
            "last_package": self.last_package,
            "last_reason": self.last_reason,
            "progress": dict(self.progress),
        }

    def as_goal_context(self, *, current_stage_id: str) -> str:
        """Prompt prefix for later stages: continuity + do-not-redo rules."""
        if not self.completed_stage_ids:
            return ""
        lines = [
            "Plan continuity (do not ignore):",
            f"- Completed stages: {', '.join(self.completed_stage_ids)}.",
            f"- Current stage id: {current_stage_id}.",
            f"- Last screen summary after prior stage: {self.last_summary or '(unknown)'}.",
            f"- Foreground package: {self.last_package or '(unknown)'}.",
            "- Do NOT redo completed stages.",
            "- Do NOT force-stop/relaunch the app or return to the app home solely to re-enter lodging/city selection unless the current screen clearly lost that context.",
            "- Prefer the smallest next UI action from the current screen toward THIS stage goal only.",
            "- Ignore ads (dismiss/back); never pay or submit an order.",
        ]
        if self.progress:
            bits = [k for k, v in self.progress.items() if v][:16]
            if bits:
                lines.append(
                    "- Accumulated progress bits (do not undo): " + ", ".join(bits) + "."
                )
            if self.progress.get("fare_seen") or self.progress.get("cart_seen"):
                lines.append(
                    "- Fare/cart already seen earlier in this plan — do not BACK/HOME away."
                )
        return "\n".join(lines)


@dataclass
class RunStage:
    id: str
    goal: str
    max_steps: int = 12
    package: str | None = None  # cold-start only when set (usually stage A)
    success_check: SuccessCheck | None = None
    tree_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "goal": self.goal,
            "max_steps": self.max_steps,
        }
        if self.package:
            out["package"] = self.package
        if self.success_check and not self.success_check.is_empty():
            out["success_check"] = self.success_check.to_dict()
        if self.tree_hints:
            out["tree_hints"] = list(self.tree_hints)
        return out

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "RunStage":
        sid = str(raw.get("id") or raw.get("name") or "").strip() or "stage"
        goal = str(raw.get("goal") or "").strip()
        if not goal:
            raise ValueError(f"stage {sid!r} missing goal")
        check_raw = raw.get("success_check")
        check = SuccessCheck.from_mapping(check_raw) if isinstance(check_raw, dict) else None
        # Allow flat keys on the stage for convenience
        if check is None:
            check = SuccessCheck.from_mapping(
                {
                    "package": raw.get("success_package"),
                    "labels_any": raw.get("success_labels_any") or raw.get("labels_any"),
                    "labels_all": raw.get("success_labels_all") or raw.get("labels_all"),
                    "use_xml": raw.get("use_xml"),
                }
            )
        hints_raw = raw.get("tree_hints") or raw.get("tree_hint") or []
        if isinstance(hints_raw, str):
            hints = [p.strip() for p in hints_raw.split(",") if p.strip()]
        else:
            hints = [str(p).strip() for p in hints_raw if str(p).strip()]
        return cls(
            id=sid,
            goal=goal,
            max_steps=int(raw.get("max_steps") or 12),
            package=(str(raw["package"]).strip() if raw.get("package") else None),
            success_check=check,
            tree_hints=hints,
        )


@dataclass
class PlanResult:
    status: str
    plan_id: str
    stages: list[dict[str, Any]] = field(default_factory=list)
    completed_stage_ids: list[str] = field(default_factory=list)
    failed_stage_id: str | None = None
    run_id: str = ""
    run_dir: str = ""
    reason: str = ""
    plan_state: dict[str, Any] | None = None
    plan_progress: dict[str, Any] | None = None
    cost_report: dict[str, Any] | None = None
    continue_hint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "status": self.status,
            "plan_id": self.plan_id,
            "completed_stage_ids": self.completed_stage_ids,
            "failed_stage_id": self.failed_stage_id,
            "reason": self.reason,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "stages": self.stages,
        }
        if self.plan_state is not None:
            out["plan_state"] = self.plan_state
        if self.plan_progress:
            out["plan_progress"] = self.plan_progress
            out["progress"] = self.plan_progress  # Host TaskState alias
        if self.cost_report is not None:
            out["cost_report"] = self.cost_report
        if self.continue_hint is not None:
            out["continue_hint"] = self.continue_hint
            out["resume"] = self.continue_hint
        from .run_loop import build_task_patch

        digest = None
        if isinstance(self.continue_hint, dict):
            maybe = self.continue_hint.get("screen_digest")
            digest = maybe if isinstance(maybe, dict) else None
        out["task_patch"] = build_task_patch(
            status=self.status,
            goal=str((self.continue_hint or {}).get("goal") or ""),
            run_id=self.run_id,
            run_dir=self.run_dir,
            progress=self.plan_progress,
            plan_progress=self.plan_progress,
            screen_digest=digest,
            resume=self.continue_hint,
            plan_id=self.plan_id,
        )
        return out


def load_plan(path: Path | str) -> tuple[str, list[RunStage]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    plan_id = str(data.get("id") or data.get("name") or Path(path).stem)
    stages_raw = data.get("stages") or []
    if not stages_raw:
        raise ValueError("plan has no stages")
    return plan_id, [RunStage.from_mapping(s) for s in stages_raw]


def android_run_plan(
    session: DeviceSession,
    stages: list[RunStage],
    *,
    plan_id: str = "plan",
    model: str | None = None,
    wall_budget_ms: int = 0,
) -> PlanResult:
    """Run stages sequentially on one session; stop on first non-OK stage.

    Between stages, ``PlanState`` (including OR-merged ``progress``) is injected
    into the next stage so facts like ``fare_seen`` survive stage boundaries.

    ``wall_budget_ms`` is passed to each stage ``android_run`` (MCP soft budget).
    """
    if not stages:
        return PlanResult(
            status="ERROR",
            plan_id=plan_id,
            run_id=session.run_id,
            run_dir=str(session.run_dir),
            reason="empty stages",
        )

    # One fresh run_dir for the whole plan; stage costs stay history-scoped.
    if hasattr(session, "begin_run"):
        session.begin_run()

    state = PlanState()
    stage_rows: list[dict[str, Any]] = []

    for idx, stage in enumerate(stages):
        ctx = state.as_goal_context(current_stage_id=stage.id)
        # package= only when the stage sets it (usually stage A cold-start).
        result: RunResult = android_run(
            session,
            stage.goal,
            max_steps=stage.max_steps,
            model=model,
            package=stage.package,
            success_check=stage.success_check,
            goal_context=ctx,
            wall_budget_ms=wall_budget_ms,
            tree_hints=list(stage.tree_hints or []),
            new_run=False,
            initial_progress=dict(state.progress),
        )
        row = {
            "id": stage.id,
            "goal": stage.goal,
            "plan_context_injected": bool(ctx),
            "result": result.to_dict(),
        }
        stage_rows.append(row)
        # Always refresh environmental memory from the latest attempt.
        state.last_summary = result.last_summary or state.last_summary
        state.last_package = result.package or state.last_package
        state.last_reason = result.reason or state.last_reason
        state.progress = _or_merge_progress(state.progress, result.progress)

        if result.status != TERMINAL_OK:
            remaining = [s.id for s in stages[idx + 1 :]]
            hint = result.continue_hint or continue_hint_for_run(
                goal=stage.goal,
                package=result.package,
                last_summary=result.last_summary,
                status=result.status,
                progress=state.progress,
                screen_digest=result.screen_digest,
                tree_hints=list(stage.tree_hints or []),
                success_check=(
                    stage.success_check.to_dict()
                    if stage.success_check and not stage.success_check.is_empty()
                    else None
                ),
            )
            # Prefer plan-accumulated progress on the ResumeSpec.
            hint = {**hint, "progress": dict(state.progress)}
            if result.status == TERMINAL_TIME_BUDGET:
                hint = {
                    **hint,
                    "failed_stage_id": stage.id,
                    "resume_stage_id": stage.id,
                    "remaining_stage_ids": [stage.id, *remaining],
                    "suggestion": (
                        f"Stage {stage.id} hit TIME_BUDGET. Re-call android_run or a short "
                        f"plan starting at stage {stage.id} from the current screen; "
                        "prefer CLI mau run-plan for very long jobs."
                    ),
                }
            return PlanResult(
                status=result.status,
                plan_id=plan_id,
                stages=stage_rows,
                completed_stage_ids=list(state.completed_stage_ids),
                failed_stage_id=stage.id,
                run_id=session.run_id,
                run_dir=str(session.run_dir),
                reason=f"stage {stage.id} → {result.status}: {result.reason}",
                plan_state=state.to_dict(),
                plan_progress=dict(state.progress) if state.progress else None,
                cost_report=plan_cost_report(stage_rows),
                continue_hint=hint,
            )
        state.completed_stage_ids.append(stage.id)

    # Success: still emit ResumeSpec so Host can checkpoint TaskState.
    last = stage_rows[-1]["result"] if stage_rows else {}
    done_hint = continue_hint_for_run(
        goal=str(last.get("goal") or stages[-1].goal),
        package=state.last_package,
        last_summary=state.last_summary,
        status=TERMINAL_OK,
        progress=state.progress,
        screen_digest=last.get("screen_digest") if isinstance(last, dict) else None,
        tree_hints=list(stages[-1].tree_hints or []),
        success_check=(
            stages[-1].success_check.to_dict()
            if stages[-1].success_check and not stages[-1].success_check.is_empty()
            else None
        ),
    )
    return PlanResult(
        status=TERMINAL_OK,
        plan_id=plan_id,
        stages=stage_rows,
        completed_stage_ids=list(state.completed_stage_ids),
        failed_stage_id=None,
        run_id=session.run_id,
        run_dir=str(session.run_dir),
        reason="all stages GOAL_REACHED",
        plan_state=state.to_dict(),
        plan_progress=dict(state.progress) if state.progress else None,
        cost_report=plan_cost_report(stage_rows),
        continue_hint=done_hint,
    )
