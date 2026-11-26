"""Phase M1 progress contract: normalize / OR-merge / prompt lines."""

from __future__ import annotations

from mano_android_use.progress import (
    cart_or_fare_hold,
    normalize_progress,
    or_merge_progress,
    progress_prompt_lines,
)
from mano_android_use.run_loop import merge_task_state, parse_progress_json
from mano_android_use.run_plan import PlanState


def test_or_merge_completed_slots_union():
    a = {"completed_slots": ["enter_store"], "saw:请输入商品名": True}
    b = {"completed_slots": ["add_sku_a", "enter_store"], "goal_matched": True}
    m = or_merge_progress(a, b)
    assert m["completed_slots"] == ["enter_store", "add_sku_a"]
    assert m["saw:请输入商品名"] is True
    assert m["goal_matched"] is True


def test_or_merge_world_cart_and_sku_keys():
    a = {"world": {"cart_count": 1, "sku_keys": ["鸭屎香柠檬茶"]}}
    b = {"world": {"cart_count": 0, "sku_keys": ["冰美式", "鸭屎香柠檬茶"]}}
    m = or_merge_progress(a, b)
    # max keeps the higher observed count; 0 must not wipe 1
    assert m["world"]["cart_count"] == 1
    assert m["world"]["sku_keys"] == ["鸭屎香柠檬茶", "冰美式"]

    m2 = or_merge_progress({"world": {"cart_count": 1}}, {"world": {"cart_count": 2}})
    assert m2["world"]["cart_count"] == 2


def test_or_merge_policy_lists():
    a = {"policy": {"banned_act_classes": ["add_same_sku"], "banned_hint_labels": ["已添加"]}}
    b = {
        "policy": {
            "banned_act_classes": ["open_spec"],
            "banned_hint_labels": ["去结算", "已添加"],
        }
    }
    m = or_merge_progress(a, b)
    assert m["policy"]["banned_act_classes"] == ["add_same_sku", "open_spec"]
    assert m["policy"]["banned_hint_labels"] == ["已添加", "去结算"]


def test_legacy_truthy_or_preserved():
    m = or_merge_progress({"fare_seen": True}, {"fare_seen": False, "opened_app": True})
    assert m["fare_seen"] is True
    assert m["opened_app"] is True


def test_normalize_and_parse_progress_json():
    raw = parse_progress_json(
        '{"completed_slots":["A"],"world":{"cart_count":"1","sku_keys":"柠檬茶"},'
        '"policy":{"banned_hint_labels":["马上抢"]},"fare_seen":true}'
    )
    assert raw["completed_slots"] == ["A"]
    assert raw["world"]["cart_count"] == 1
    assert raw["world"]["sku_keys"] == ["柠檬茶"]
    assert raw["policy"]["banned_hint_labels"] == ["马上抢"]
    assert raw["fare_seen"] is True
    assert normalize_progress(None) == {}


def test_merge_task_state_uses_contract_merge():
    state = {"progress": {"completed_slots": ["enter"], "world": {"cart_count": 1}}}
    patch = {
        "progress": {
            "completed_slots": ["add"],
            "world": {"sku_keys": ["柠檬茶"]},
            "policy": {"banned_hint_labels": ["已添加"]},
        },
        "status": "GOAL_REACHED",
    }
    out = merge_task_state(state, patch)
    assert out["progress"]["completed_slots"] == ["enter", "add"]
    assert out["progress"]["world"]["cart_count"] == 1
    assert out["progress"]["world"]["sku_keys"] == ["柠檬茶"]
    assert out["progress"]["policy"]["banned_hint_labels"] == ["已添加"]
    assert out["status"] == "GOAL_REACHED"


def test_progress_prompt_and_plan_context():
    prog = {
        "completed_slots": ["A_enter_store", "B_add_single_cup"],
        "world": {"cart_count": 1, "sku_keys": ["鸭屎香柠檬茶"]},
        "policy": {
            "banned_act_classes": ["add_same_sku"],
            "banned_hint_labels": ["选规格"],
        },
        "cart_seen": True,
    }
    text = "\n".join(progress_prompt_lines(prog))
    assert "Completed slots" in text
    assert "A_enter_store" in text
    assert "cart_count=1" in text
    assert "鸭屎香柠檬茶" in text
    assert "Banned act classes" in text
    assert "Banned hint labels" in text
    assert "Progress hold" in text
    assert cart_or_fare_hold(prog) is True

    ctx = PlanState(
        completed_stage_ids=["A_enter_store"],
        last_summary="menu",
        last_package="com.sankuai.meituan",
        progress=prog,
    ).as_goal_context(current_stage_id="C_verify_cart")
    assert "Do NOT redo completed stages" in ctx
    assert "Completed slots" in ctx
    assert "Banned hint labels" in ctx
