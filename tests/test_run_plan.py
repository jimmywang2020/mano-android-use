from pathlib import Path

from mano_android_use.run_loop import TERMINAL_OK, TERMINAL_TIME_BUDGET, RunResult
from mano_android_use.run_plan import RunStage, android_run_plan, load_plan
from mano_android_use.success_check import SuccessCheck


def test_load_ctrip_plan():
    root = Path(__file__).resolve().parents[1]
    plan_id, stages = load_plan(root / "docs/examples/plans/ctrip-beijing-homestay.json")
    assert plan_id == "ctrip-beijing-homestay"
    assert [s.id for s in stages] == ["A_enter_lodging", "B_city_beijing", "C_price_list"]
    assert stages[0].package == "ctrip.android.view"
    assert stages[2].success_check and "¥" in stages[2].success_check.labels_any


def test_plan_stops_on_stage_failure(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")

    calls: list[str] = []

    def _fake_run(session, goal, **kwargs):
        calls.append(goal)
        if len(calls) == 1:
            return RunResult(
                status=TERMINAL_OK,
                goal=goal,
                steps=1,
                model="fake",
                run_id="r",
                run_dir="/tmp",
                reason="ok",
                last_summary="summary-A",
                package="app.demo",
                cost_report={
                    "total_ms": 1000,
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                    "dominant_phase": "grounder",
                    "by_phase": {
                        "observe": {"ms": 100, "pct": 10},
                        "grounder": {"ms": 800, "pct": 80},
                        "act": {"ms": 100, "pct": 10},
                    },
                    "narrative": "stage A cost",
                },
            )
        return RunResult(
            status="STUCK",
            goal=goal,
            steps=2,
            model="fake",
            run_id="r",
            run_dir="/tmp",
            reason="stuck",
            last_summary="summary-B",
            package="app.demo",
            cost_report={
                "total_ms": 500,
                "prompt_tokens": 5,
                "completion_tokens": 1,
                "dominant_phase": "observe",
                "by_phase": {
                    "observe": {"ms": 400, "pct": 80},
                    "grounder": {"ms": 100, "pct": 20},
                    "act": {"ms": 0, "pct": 0},
                },
                "narrative": "stage B cost",
            },
        )

    monkeypatch.setattr("mano_android_use.run_plan.android_run", _fake_run)
    stages = [
        RunStage(id="A", goal="a", success_check=SuccessCheck(labels_any=["x"])),
        RunStage(id="B", goal="b", success_check=SuccessCheck(labels_any=["y"])),
        RunStage(id="C", goal="c"),
    ]
    res = android_run_plan(_S(), stages, plan_id="t")
    assert res.status == "STUCK"
    assert res.failed_stage_id == "B"
    assert res.completed_stage_ids == ["A"]
    assert len(calls) == 2
    assert res.cost_report is not None
    assert res.cost_report["total_ms"] == 1500
    assert res.cost_report["prompt_tokens"] == 15
    assert len(res.cost_report["stages"]) == 2


def test_plan_injects_continuity_context(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")

    contexts: list[str] = []
    seeds: list[dict] = []

    def _fake_run(session, goal, **kwargs):
        contexts.append(str(kwargs.get("goal_context") or ""))
        seeds.append(dict(kwargs.get("initial_progress") or {}))
        n = len(contexts)
        prog = {"opened_app": True} if n == 1 else {"fare_seen": True, "saw:一口价": True}
        return RunResult(
            status=TERMINAL_OK,
            goal=goal,
            steps=1,
            model="fake",
            run_id="r",
            run_dir="/tmp",
            reason="ok",
            last_summary=f"sum-{n}",
            package="ctrip.android.view",
            progress=prog,
        )

    monkeypatch.setattr("mano_android_use.run_plan.android_run", _fake_run)
    stages = [
        RunStage(id="A", goal="enter"),
        RunStage(id="B", goal="city"),
        RunStage(id="C", goal="prices"),
    ]
    res = android_run_plan(_S(), stages, plan_id="t")
    assert res.status == TERMINAL_OK
    assert contexts[0] == ""
    assert "Completed stages: A" in contexts[1]
    assert "Do NOT redo completed stages" in contexts[1]
    assert "sum-1" in contexts[1]
    assert "Completed stages: A, B" in contexts[2]
    assert "sum-2" in contexts[2]
    assert res.stages[1]["plan_context_injected"] is True
    assert res.plan_state and res.plan_state["completed_stage_ids"] == ["A", "B", "C"]
    # Stage B/C receive OR-merged progress from prior stages.
    assert seeds[0] == {}
    assert seeds[1].get("opened_app") is True
    assert seeds[2].get("opened_app") is True
    assert seeds[2].get("fare_seen") is True
    assert res.plan_progress and res.plan_progress.get("fare_seen") is True
    assert "fare_seen" in contexts[2] or "Accumulated progress" in contexts[2]
    assert res.continue_hint and res.continue_hint.get("next_actor") == "done"
    assert res.to_dict().get("resume", {}).get("next_actor") == "done"


def test_plan_state_prompt_rules():
    from mano_android_use.run_plan import PlanState

    ctx = PlanState(
        completed_stage_ids=["A_enter_lodging", "B_city_beijing"],
        last_summary="package=ctrip; labels=[北京, 民宿]",
        last_package="ctrip.android.view",
    ).as_goal_context(current_stage_id="C_price_list")
    assert "Completed stages: A_enter_lodging, B_city_beijing" in ctx
    assert "Current stage id: C_price_list" in ctx
    assert "Do NOT redo" in ctx
    assert "北京" in ctx


def test_plan_stops_on_time_budget_with_continue_hint(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")

    budgets: list[int] = []

    def _fake_run(session, goal, **kwargs):
        budgets.append(int(kwargs.get("wall_budget_ms") or 0))
        if len(budgets) == 1:
            return RunResult(
                status=TERMINAL_OK,
                goal=goal,
                steps=1,
                model="fake",
                run_id="r",
                run_dir="/tmp",
                reason="ok",
                last_summary="sum-A",
                package="app.demo",
                cost_report={
                    "total_ms": 100,
                    "prompt_tokens": 1,
                    "completion_tokens": 0,
                    "dominant_phase": "observe",
                    "by_phase": {
                        "observe": {"ms": 100, "pct": 100},
                        "grounder": {"ms": 0, "pct": 0},
                        "act": {"ms": 0, "pct": 0},
                    },
                    "narrative": "A",
                },
            )
        return RunResult(
            status=TERMINAL_TIME_BUDGET,
            goal=goal,
            steps=2,
            model="fake",
            run_id="r",
            run_dir="/tmp",
            reason="wall_budget_ms=90000",
            last_summary="sum-B",
            package="app.demo",
            continue_hint={"action": "android_run", "goal": goal},
            cost_report={
                "total_ms": 200,
                "prompt_tokens": 2,
                "completion_tokens": 0,
                "dominant_phase": "grounder",
                "by_phase": {
                    "observe": {"ms": 50, "pct": 25},
                    "grounder": {"ms": 150, "pct": 75},
                    "act": {"ms": 0, "pct": 0},
                },
                "narrative": "B budget",
            },
        )

    monkeypatch.setattr("mano_android_use.run_plan.android_run", _fake_run)
    stages = [
        RunStage(id="A", goal="a"),
        RunStage(id="B", goal="b"),
        RunStage(id="C", goal="c"),
    ]
    res = android_run_plan(_S(), stages, plan_id="t", wall_budget_ms=90_000)
    assert res.status == TERMINAL_TIME_BUDGET
    assert res.failed_stage_id == "B"
    assert res.completed_stage_ids == ["A"]
    assert budgets == [90_000, 90_000]
    assert res.cost_report is not None
    assert res.cost_report["total_ms"] == 300
    assert res.continue_hint is not None
    assert res.continue_hint.get("resume_stage_id") == "B"
    assert res.continue_hint.get("remaining_stage_ids") == ["B", "C"]
