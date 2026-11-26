"""Phase M3 Host SlotSpec thin lib."""

from __future__ import annotations

from pathlib import Path

from mano_android_use.host_slots import (
    SlotSpec,
    build_android_run_args,
    host_step,
    load_slot_graph,
    next_slot,
    on_done,
    slot_peek,
    slots_from_plan_stages,
)

ROOT = Path(__file__).resolve().parents[1]
SLOTS = ROOT / "docs" / "examples" / "slots"
PLANS = ROOT / "docs" / "examples" / "plans"


def test_next_slot_linear_and_on_done_replaces_hints():
    graph = load_slot_graph(SLOTS / "meituan-dual-drink.slots.json")
    prog: dict = {}
    a = next_slot(graph, prog)
    assert a is not None and a.id == "A_enter_store"
    assert a.package == "com.sankuai.meituan"
    args_a = build_android_run_args(a, prog)
    assert args_a.omit_package is False
    assert "外卖" in args_a.tree_hints
    assert "点菜" not in (a.done_when.get("labels_any") or [])

    prog = on_done(prog, a)
    assert prog["completed_slots"] == ["A_enter_store"]

    # Phase P1: optional A2_open_menu between enter and first acquire
    a2 = next_slot(graph, prog)
    assert a2 is not None and a2.id == "A2_open_menu"
    peek = slot_peek(graph, prog)
    assert peek["done"] is False
    assert "选规格" in peek["suggested_find"]
    prog = on_done(prog, a2)  # Host skip when find already saw menu

    b = next_slot(graph, prog)
    assert b is not None and b.id == "B_add_lemon_tea"
    args_b = build_android_run_args(b, prog)
    assert args_b.omit_package is True
    assert args_b.tree_hints[0] == "柠檬茶"  # SKU-first (P2)
    assert "选规格" in args_b.tree_hints
    mcp = args_b.to_mcp_arguments()
    assert "package" not in mcp
    assert "柠檬茶" in mcp["tree_hints"]
    assert "已添加" in mcp["success_labels_any"]

    prog = on_done(prog, b)
    assert "柠檬茶" in prog["world"]["sku_keys"]
    assert prog["world"]["cart_count"] == 1
    assert "已添加" in prog["policy"]["banned_hint_labels"]

    c = next_slot(graph, prog)
    assert c is not None and c.id == "C_add_second_drink"
    # Hints replaced — not inherited bare 选规格-only from B without 奶茶
    assert c.hints[0] == "奶茶"
    assert "柠檬茶" not in c.hints

    prog = on_done(prog, c)
    assert set(prog["world"]["sku_keys"]) >= {"柠檬茶", "奶茶"}
    assert prog["world"]["cart_count"] == 2

    d = next_slot(graph, prog)
    assert d is not None and d.id == "D_verify_cart"
    assert d.hints == []
    prog = on_done(prog, d)
    assert next_slot(graph, prog) is None
    step = host_step(graph, prog)
    assert step["done"] is True
    assert slot_peek(graph, prog)["done"] is True


def test_didi_and_meituan_share_same_next_slot_api():
    meituan = load_slot_graph(SLOTS / "meituan-dual-drink.slots.json")
    didi = load_slot_graph(SLOTS / "didi-airport-fare.slots.json")
    # Identical control flow — only SlotSpec data differs
    for graph, first_id in ((meituan, "A_enter_store"), (didi, "A_open_didi")):
        prog: dict = {}
        slot = next_slot(graph, prog)
        assert slot is not None and slot.id == first_id
        prog = on_done(prog, slot)
        slot2 = next_slot(graph, prog)
        assert slot2 is not None
        assert first_id in slot2.depends_on
        args = build_android_run_args(slot2, prog)
        assert args.omit_package is True
        assert args.slot_id == slot2.id


def test_slots_from_plan_stages_linear_depends():
    import json

    plan = json.loads((PLANS / "didi-airport-carpool-vs-special.json").read_text())
    slots = slots_from_plan_stages(plan["stages"])
    assert [s.id for s in slots] == [
        "A_open_didi",
        "B_set_dest_airport",
        "C_read_carpool_and_special",
    ]
    assert slots[1].depends_on == ["A_open_didi"]
    assert slots[2].depends_on == ["B_set_dest_airport"]
    # load_slot_graph accepts plan JSON too
    g = load_slot_graph(PLANS / "meituan-lemon-tea-cart.json")
    assert g.slots[0].id == "A_enter_store"
    assert next_slot(g, {}) is not None


def test_slot_spec_from_mapping_aliases():
    s = SlotSpec.from_mapping(
        {
            "id": "x",
            "goal": "g",
            "tree_hints": "a,b",
            "success_check": {"labels_all": ["去结算"]},
            "depends_on": "p",
        }
    )
    assert s.hints == ["a", "b"]
    assert s.done_when["labels_all"] == ["去结算"]
    assert s.depends_on == ["p"]
