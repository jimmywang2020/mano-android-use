from pathlib import Path

from mano_android_use.run_loop import TERMINAL_OK, RunResult
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


def test_plan_injects_continuity_context(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")

    contexts: list[str] = []

    def _fake_run(session, goal, **kwargs):
        contexts.append(str(kwargs.get("goal_context") or ""))
        n = len(contexts)
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
