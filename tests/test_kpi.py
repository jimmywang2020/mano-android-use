"""Phase M5 anti-redo KPIs."""

from __future__ import annotations

from mano_android_use.kpi import (
    format_kpi_table,
    kpi_narrative,
    kpis_from_history,
    kpis_from_spans,
)
from mano_android_use.trace_report import cost_report_from_history


def test_kpis_guard_noop_and_redo_from_history():
    history = [
        {
            "step": 1,
            "timing": {"via": "tree_shortcut", "action": "click", "act_ms": 0},
            "skip_reason": "guard_noop",
            "guard": {
                "act_class": "open_spec",
                "target_key": "柠檬茶",
                "code": "GUARD_NOOP",
            },
            "execution": {"ok": True, "code": "GUARD_NOOP", "guard": True},
            "progress": {"world": {"sku_keys": ["柠檬茶"], "cart_count": 1}, "cart_seen": True},
        },
        {
            "step": 2,
            "timing": {"via": "tree_shortcut", "action": "click", "act_ms": 12},
            "tree_shortcut": {"query": "选规格"},
            "guard": {"act_class": "open_spec", "target_key": "柠檬茶", "code": "OK"},
            "action": {"action": "click", "text": "选规格"},
            "execution": {"ok": True, "via": "tree_shortcut"},
            "progress": {"cart_seen": True, "world": {"cart_count": 1, "sku_keys": ["柠檬茶"]}},
        },
        {
            "step": 3,
            "timing": {"via": "tree_shortcut", "action": "click", "act_ms": 10},
            "tree_shortcut": {"query": "选规格"},
            "guard": {"act_class": "open_spec", "target_key": "柠檬茶", "code": "OK"},
            "action": {"action": "click", "text": "选规格"},
            "execution": {"ok": True, "via": "tree_shortcut"},
            "progress": {"cart_seen": True},
        },
    ]
    k = kpis_from_history(history)
    assert k["guard_noop"] == 1
    assert k["redo_same_act_class"] == 1  # second executed open_spec+柠檬茶
    assert k["acquire_after_cart"] >= 1
    report = cost_report_from_history(history)
    assert report["kpis"]["guard_noop"] == 1
    assert "KPIs:" in (report.get("narrative") or "")


def test_kpis_from_spans_l0_share():
    spans = [
        {"event": "android_run_step", "via": "android_run", "step": 1, "act_ms": 5},
        {"event": "android_run_step", "via": "tree_shortcut", "step": 2, "act_ms": 5},
        {"event": "l0_step", "via": "l0_direct", "step": 3, "act_ms": 2},
        {
            "event": "android_run_step",
            "via": "tree_shortcut",
            "skip_reason": "guard_noop",
            "act_class": "open_spec",
            "target_key": "x",
            "act_ms": 0,
        },
    ]
    k = kpis_from_spans(spans)
    assert k["android_run_steps"] == 3
    assert k["l0_steps"] == 1
    assert k["l0_as_main_loop_share_pct"] == 25.0
    assert k["guard_noop"] == 1
    assert "l0_share=25.0%" in kpi_narrative(k)
    assert "guard_noop" in format_kpi_table(k)
