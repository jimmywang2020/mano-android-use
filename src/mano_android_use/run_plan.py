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

from .run_loop import TERMINAL_OK, RunResult, android_run
from .session import DeviceSession
from .success_check import SuccessCheck


@dataclass
class PlanState:
    """Thin cross-stage memory (LangGraph-style state, without LangGraph)."""

    completed_stage_ids: list[str] = field(default_factory=list)
    last_summary: str = ""
    last_package: str = ""
    last_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed_stage_ids": list(self.completed_stage_ids),
            "last_summary": self.last_summary,
            "last_package": self.last_package,
            "last_reason": self.last_reason,
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
        return "\n".join(lines)


@dataclass
class RunStage:
    id: str
    goal: str
    max_steps: int = 12
    package: str | None = None  # cold-start only when set (usually stage A)
    success_check: SuccessCheck | None = None

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
        return cls(
            id=sid,
            goal=goal,
            max_steps=int(raw.get("max_steps") or 12),
            package=(str(raw["package"]).strip() if raw.get("package") else None),
            success_check=check,
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
) -> PlanResult:
    """Run stages sequentially on one session; stop on first non-OK stage.

    Between stages, ``PlanState`` is injected into the next stage's grounder
    prompt so the model continues from the current screen.
    """
    if not stages:
        return PlanResult(
            status="ERROR",
            plan_id=plan_id,
            run_id=session.run_id,
            run_dir=str(session.run_dir),
            reason="empty stages",
        )

    state = PlanState()
    stage_rows: list[dict[str, Any]] = []

    for stage in stages:
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

        if result.status != TERMINAL_OK:
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
            )
        state.completed_stage_ids.append(stage.id)

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
    )
