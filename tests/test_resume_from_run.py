"""Phase O4 resume_from_run — journal draft, never GOAL-count as cart_count."""

from __future__ import annotations

import json
from pathlib import Path

from mano_android_use.resume_from_run import resume_from_run

SLOTS = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "examples"
    / "slots"
    / "meituan-dual-drink.slots.json"
)


def _write_journal(run_dir: Path, rows: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "journal.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_cart_count_from_a11y_not_goal_events(tmp_path: Path):
    run = tmp_path / "runs" / "20261126-test-one"
    _write_journal(
        run,
        [
            {
                "event": "android_run_stop",
                "status": "GOAL_REACHED",
                "summary": "labels=[选规格]",
            },
            {
                "event": "android_run_stop",
                "status": "GOAL_REACHED",
                "summary": "labels=[去结算, 购物车，已添加1件商品，点击查看]",
            },
            {
                "event": "android_run_stop",
                "status": "GOAL_REACHED",
                "summary": "labels=[去结算, 已添加]",  # weak — still 1件 blob preferred below
            },
            {
                "event": "observe",
                "summary": "package=meituan; labels=[去结算, 购物车，已添加1件商品，点击查看]",
                "package": "com.sankuai.meituan",
            },
        ],
    )
    out = resume_from_run(run, runs_root=tmp_path / "runs", slots_path=SLOTS)
    assert out["ok"]
    assert out["goal_reached_stop_count"] == 3
    assert out["draft_progress"]["world"]["cart_count"] == 1
    assert "do NOT use that count as cart_count" in " ".join(out["warnings"])
    assert out["draft_progress"]["completed_slots"] == [
        "A_enter_store",
        "A2_open_menu",
        "B_add_lemon_tea",
    ]
    assert "C_add_second_drink" not in out["draft_progress"]["completed_slots"]
    assert out["mcp_hint"]["omit_package"] is True
    assert out["mcp_hint"]["cold_start"] is False
    assert "completed_slots" in out["needs_confirm"] or "completed_slots_heuristic" in out[
        "needs_confirm"
    ]


def test_two_items_suggests_through_c_not_d(tmp_path: Path):
    run = tmp_path / "runs" / "20261126-test-two"
    _write_journal(
        run,
        [
            {
                "event": "android_run_stop",
                "status": "TIME_BUDGET",
                "summary": "购物车，已添加2件商品，点击查看；去结算；奶茶",
                "package": "com.sankuai.meituan",
            },
        ],
    )
    out = resume_from_run(run, runs_root=tmp_path / "runs", slots_path=SLOTS)
    assert out["ok"]
    assert out["draft_progress"]["world"]["cart_count"] == 2
    slots = out["draft_progress"]["completed_slots"]
    assert slots == [
        "A_enter_store",
        "A2_open_menu",
        "B_add_lemon_tea",
        "C_add_second_drink",
    ]
    assert "D_verify_cart" not in slots


def test_no_cart_phrase_leaves_count_unknown(tmp_path: Path):
    run = tmp_path / "runs" / "20261126-test-empty"
    _write_journal(
        run,
        [{"event": "android_run_stop", "status": "STUCK", "summary": "labels=[搜索]"}],
    )
    out = resume_from_run(run, runs_root=tmp_path / "runs")
    assert out["ok"]
    assert "world" not in out["draft_progress"] or "cart_count" not in out[
        "draft_progress"
    ].get("world", {})
    assert any("cart_count unknown" in w for w in out["warnings"])


def test_cart_count_from_step_xml_when_journal_omits_badge(tmp_path: Path):
    run = tmp_path / "runs" / "20261126-test-xml"
    _write_journal(
        run,
        [
            {
                "event": "android_run_stop",
                "status": "GOAL_REACHED",
                "summary": "labels=[点菜, 选规格]",
                "package": "com.sankuai.meituan",
            }
        ],
    )
    (run / "step-03.xml").write_text(
        '<node content-desc="购物车，已添加2件商品，点击查看"/>',
        encoding="utf-8",
    )
    out = resume_from_run(run, runs_root=tmp_path / "runs", slots_path=SLOTS)
    assert out["ok"]
    assert out["draft_progress"]["world"]["cart_count"] == 2
    assert out["draft_progress"]["completed_slots"] == [
        "A_enter_store",
        "A2_open_menu",
        "B_add_lemon_tea",
        "C_add_second_drink",
    ]
