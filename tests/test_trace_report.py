import json
from pathlib import Path

from mano_android_use.apply_action import VIA_ANDROID_RUN, VIA_L0_DIRECT
from mano_android_use.trace_report import (
    EVENT_L0_STEP,
    EVENT_PROPOSE_STEP,
    EVENT_STEP,
    aggregate_totals,
    build_step_span,
    cost_report_from_doc,
    format_trace_table,
    load_step_spans,
    load_trace,
    plan_cost_report,
    resolve_trace_target,
    spans_from_history,
    write_trace,
)


def test_build_step_span_sums_step_ms():
    span = build_step_span(
        step=2,
        model="m",
        observe_ms=100,
        grounder_ms=200,
        act_ms=50,
        prompt_tokens=10,
        completion_tokens=3,
        grounder_calls=1,
        action="click",
    )
    assert span["event"] == EVENT_STEP
    assert span["step_ms"] == 350
    assert span["prompt_tokens"] == 10


def test_aggregate_and_load_from_journal(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    rows = [
        {"event": "observe", "step": 1},
        build_step_span(
            step=1,
            model="m",
            observe_ms=10,
            grounder_ms=20,
            act_ms=5,
            prompt_tokens=100,
            completion_tokens=4,
            action="click",
        ),
        build_step_span(
            step=2,
            model="m",
            observe_ms=11,
            grounder_ms=0,
            act_ms=0,
            action="terminate",
        ),
        {"event": "android_run_stop", "status": "GOAL_REACHED"},
    ]
    with journal.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    steps = load_step_spans(tmp_path)
    assert len(steps) == 2
    totals = aggregate_totals(steps)
    assert totals["steps"] == 2
    assert totals["observe_ms"] == 21
    assert totals["grounder_ms"] == 20
    assert totals["prompt_tokens"] == 100

    doc = write_trace(
        tmp_path,
        run_id="r1",
        goal="g",
        status="GOAL_REACHED",
        model="m",
    )
    assert (tmp_path / "trace.json").is_file()
    assert doc["totals"]["step_ms"] == 46
    loaded = load_trace(tmp_path)
    assert loaded["run_id"] == "r1"
    table = format_trace_table(loaded)
    assert "vlm_ms" in table
    assert "click" in table


def test_spans_from_history_fallback_and_missing_fields():
    history = [
        {"step": 1, "timing": {"observe_ms": 1, "grounder_ms": 2, "act_ms": 3}},
        {"step": 2},
    ]
    spans = spans_from_history(history)
    assert len(spans) == 1
    assert spans[0]["event"] == EVENT_STEP
    totals = aggregate_totals([{"observe_ms": None, "bogus": 1}])
    assert totals["observe_ms"] == 0
    assert totals["steps"] == 1


def test_cost_report_narrative_and_plan_rollup():
    doc = {
        "steps": [
            build_step_span(
                step=1,
                model="m",
                observe_ms=100,
                grounder_ms=800,
                act_ms=100,
                prompt_tokens=50,
                completion_tokens=5,
                action="click",
            )
        ]
    }
    doc["totals"] = aggregate_totals(doc["steps"])
    cr = cost_report_from_doc(doc)
    assert cr["dominant_phase"] == "grounder"
    assert cr["by_phase"]["grounder"]["pct"] == 80.0
    assert "VLM" in cr["narrative"] or "grounder" in cr["narrative"]

    plan = plan_cost_report(
        [
            {
                "id": "A",
                "goal": "open",
                "result": {"status": "GOAL_REACHED", "cost_report": cr},
            },
            {
                "id": "B",
                "goal": "search",
                "result": {
                    "status": "GOAL_REACHED",
                    "cost_report": cost_report_from_doc(
                        {
                            "steps": [
                                build_step_span(
                                    step=1,
                                    model="m",
                                    observe_ms=50,
                                    grounder_ms=50,
                                    act_ms=0,
                                    prompt_tokens=10,
                                    completion_tokens=1,
                                )
                            ],
                            "totals": aggregate_totals(
                                [
                                    build_step_span(
                                        step=1,
                                        model="m",
                                        observe_ms=50,
                                        grounder_ms=50,
                                        act_ms=0,
                                        prompt_tokens=10,
                                        completion_tokens=1,
                                    )
                                ]
                            ),
                        }
                    ),
                },
            },
        ]
    )
    assert plan["total_ms"] == 1100
    assert plan["prompt_tokens"] == 60
    assert len(plan["stages"]) == 2
    assert "stage" in plan["narrative"].lower() or "Plan total" in plan["narrative"]


def test_by_via_propose_and_l0_spans(tmp_path: Path):
    rows = [
        build_step_span(
            step=1,
            model="m",
            observe_ms=10,
            grounder_ms=100,
            act_ms=5,
            prompt_tokens=20,
            completion_tokens=2,
            action="click",
            via="android_run",
            event=EVENT_STEP,
        ),
        build_step_span(
            step=2,
            model="m",
            observe_ms=8,
            grounder_ms=40,
            act_ms=0,
            prompt_tokens=5,
            completion_tokens=1,
            action="click",
            via="propose",
            event=EVENT_PROPOSE_STEP,
        ),
        build_step_span(
            step=3,
            model="",
            observe_ms=0,
            grounder_ms=0,
            act_ms=12,
            action="click",
            via="l0_direct",
            event=EVENT_L0_STEP,
        ),
    ]
    journal = tmp_path / "journal.jsonl"
    with journal.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
        # android_run L0 act row must NOT be treated as a span by itself
        fh.write(
            json.dumps({"event": "tap", "xy": [1, 2], "via": VIA_ANDROID_RUN, "act_ms": 3})
            + "\n"
        )

    steps = load_step_spans(tmp_path)
    assert len(steps) == 3
    totals = aggregate_totals(steps)
    assert set(totals["by_via"]) == {"android_run", "propose", "l0_direct"}
    assert totals["by_via"]["android_run"]["steps"] == 1
    assert totals["by_via"]["propose"]["prompt_tokens"] == 5
    assert totals["by_via"]["l0_direct"]["step_ms"] == 12
    cr = cost_report_from_doc({"steps": steps, "totals": totals})
    assert "by_via" in cr
    assert "bypass" in cr["narrative"].lower() or "L0" in cr["narrative"]
    table = format_trace_table(
        write_trace(tmp_path, run_id="r", goal="g", status="OK", model="m")
    )
    assert "via" in table
    assert "l0_direct" in table
    assert "by_via" in table


def test_l0_span_skipped_for_android_run_via(tmp_path: Path):
    """Session helper only emits l0_step for VIA_L0_DIRECT."""
    from mano_android_use.session import DeviceSession

    session = DeviceSession(
        serial="fake",
        run_dir=tmp_path,
        adb=None,  # type: ignore[arg-type]
    )
    session._log_l0_span_if_direct(action="click", act_ms=9, via=VIA_ANDROID_RUN)
    session._log_l0_span_if_direct(action="click", act_ms=11, via=VIA_L0_DIRECT)
    spans = [e for e in session._journal if e.get("event") == EVENT_L0_STEP]
    assert len(spans) == 1
    assert spans[0]["act_ms"] == 11
    assert spans[0]["via"] == VIA_L0_DIRECT


def test_resolve_trace_target_newest(tmp_path: Path):
    older = tmp_path / "old"
    newer = tmp_path / "new"
    older.mkdir()
    newer.mkdir()
    (older / "journal.jsonl").write_text("{}\n", encoding="utf-8")
    (newer / "journal.jsonl").write_text("{}\n", encoding="utf-8")
    # Ensure newer mtime
    newer.joinpath("marker").write_text("x", encoding="utf-8")
    got = resolve_trace_target(None, runs_root=tmp_path)
    assert got == newer
    assert resolve_trace_target(str(newer), runs_root=tmp_path) == newer
    trace = newer / "trace.json"
    trace.write_text("{}", encoding="utf-8")
    assert resolve_trace_target(str(trace), runs_root=tmp_path) == newer
