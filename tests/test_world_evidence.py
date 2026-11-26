"""Phase M4 world evidence + DONE gates."""

from __future__ import annotations

import json
from pathlib import Path

from mano_android_use.progress import or_merge_progress
from mano_android_use.success_check import SuccessCheck, evaluate_success
from mano_android_use.world_evidence import extract_cart_count, suggest_world_progress

PLANS = Path(__file__).resolve().parents[1] / "docs" / "examples" / "plans"


def test_extract_cart_count_from_meituan_phrases():
    assert extract_cart_count("购物车，已添加1件商品，点击查看") == 1
    assert extract_cart_count("已添加 2 件") == 2
    assert extract_cart_count("labels=[柠檬茶, 选规格]") is None


def test_suggest_world_progress_sets_cart_count_and_cart_seen():
    frag = suggest_world_progress(
        summary="package=meituan; labels=[去结算]",
        labels=["购物车，已添加1件商品，点击查看", "去结算", "鸭屎香柠檬茶"],
    )
    assert frag["world"]["cart_count"] == 1
    assert frag["cart_seen"] is True
    merged = or_merge_progress({"world": {"sku_keys": ["鸭屎香柠檬茶"]}}, frag)
    assert merged["world"]["cart_count"] == 1
    assert merged["world"]["sku_keys"] == ["鸭屎香柠檬茶"]


def test_search_page_product_name_alone_not_done():
    """Menu/search listing with 柠檬茶 must fail terminal world-state gate."""
    check = SuccessCheck(
        package="com.sankuai.meituan",
        labels_all=["去结算", "已添加"],
        labels_any=["柠檬茶", "手打柠檬"],
        forbid_labels=["立即支付", "确认支付"],
    )
    search = evaluate_success(
        check,
        package="com.sankuai.meituan",
        summary="package=com.sankuai.meituan; labels=[搜索, 柠檬茶, LINLEE林里·手打柠檬茶, ¥11.4]",
        xml="",
    )
    assert not search.ok
    assert any("labels_all missing" in r for r in search.reasons)

    cart = evaluate_success(
        check,
        package="com.sankuai.meituan",
        summary=(
            "package=com.sankuai.meituan; labels=[去结算, 购物车，已添加1件商品，点击查看, "
            "鸭屎香柠檬茶【招牌】]"
        ),
        xml="",
    )
    assert cart.ok
    assert "去结算" in cart.matched
    assert "已添加" in cart.matched or any("已添加" in m for m in cart.matched)


def test_loose_到手约_must_not_be_sole_add_gate():
    """B-stage should not DONE on menu price band alone."""
    tight = SuccessCheck(
        package="com.sankuai.meituan",
        labels_any=["已添加", "去结算"],
        forbid_labels=["立即支付"],
    )
    menu = evaluate_success(
        tight,
        package="com.sankuai.meituan",
        summary="labels=[清新手打柠檬茶, 到手约, ¥11.4, 选规格]",
        xml="",
    )
    assert not menu.ok


def test_production_plans_terminal_have_world_state_labels_all():
    for name in ("meituan-lemon-tea-cart.json", "meituan-dual-drink-cart.json"):
        plan = json.loads((PLANS / name).read_text(encoding="utf-8"))
        assert plan.get("role") == "production"
        terminal = plan["stages"][-1]
        check = terminal["success_check"]
        all_labs = check.get("labels_all") or []
        assert "去结算" in all_labs
        assert any("已添加" in str(x) for x in all_labs)
        hints = terminal.get("tree_hints") or []
        assert "已添加" not in hints
        assert "去结算" not in hints


def test_dual_drink_store_header_diancai_not_a_done():
    """Phase P1: bare「点菜」tab selected must not GOAL A_enter_store."""
    plan = json.loads((PLANS / "meituan-dual-drink-cart.json").read_text(encoding="utf-8"))
    stages = {s["id"]: s for s in plan["stages"]}
    a_check = SuccessCheck.from_mapping(stages["A_enter_store"]["success_check"])
    assert a_check is not None
    assert "点菜" not in (a_check.labels_any or [])
    header = (
        "package=com.sankuai.meituan; labels=[点菜 已选中, 评价, 商家, "
        "LINLEE林里·手打柠檬茶, 收藏]"
    )
    bad = evaluate_success(
        a_check, package="com.sankuai.meituan", summary=header, xml=""
    )
    assert not bad.ok, "store-header 点菜 alone must fail A"
    menu = (
        "package=com.sankuai.meituan; labels=[选规格, 请输入商品名, "
        "鸭屎香柠檬茶【招牌】, 点菜]"
    )
    assert evaluate_success(
        a_check, package="com.sankuai.meituan", summary=menu, xml=""
    ).ok
    # A2 exists and also rejects header-only
    assert "A2_open_menu" in stages
    a2 = SuccessCheck.from_mapping(stages["A2_open_menu"]["success_check"])
    assert a2 is not None
    assert not evaluate_success(
        a2, package="com.sankuai.meituan", summary=header, xml=""
    ).ok
    assert evaluate_success(
        a2, package="com.sankuai.meituan", summary=menu, xml=""
    ).ok


def test_dual_drink_one_item_screen_fails_c_and_d():
    """Phase O1: bare「已添加」on 1-item cart must not GOAL C/D (live miss 154056)."""
    plan = json.loads((PLANS / "meituan-dual-drink-cart.json").read_text(encoding="utf-8"))
    stages = {s["id"]: s for s in plan["stages"]}
    one_item = (
        "package=com.sankuai.meituan; labels=[去结算, 购物车，已添加1件商品，点击查看, "
        "鸭屎香柠檬茶【招牌】, 选规格]"
    )
    two_item = (
        "package=com.sankuai.meituan; labels=[去结算, 购物车，已添加2件商品，点击查看, "
        "鸭屎香柠檬茶【招牌】, 奶茶]"
    )
    for sid in ("C_add_second_drink", "D_verify_cart"):
        check = SuccessCheck.from_mapping(stages[sid]["success_check"])
        assert check is not None
        bad = evaluate_success(
            check, package="com.sankuai.meituan", summary=one_item, xml=""
        )
        assert not bad.ok, f"{sid} must fail on 1-item cart"
    c_check = SuccessCheck.from_mapping(stages["C_add_second_drink"]["success_check"])
    d_check = SuccessCheck.from_mapping(stages["D_verify_cart"]["success_check"])
    assert c_check and d_check
    assert evaluate_success(
        c_check, package="com.sankuai.meituan", summary=two_item, xml=""
    ).ok
    assert evaluate_success(
        d_check, package="com.sankuai.meituan", summary=two_item, xml=""
    ).ok
    b_check = SuccessCheck.from_mapping(stages["B_add_lemon_tea"]["success_check"])
    assert b_check
    assert evaluate_success(
        b_check, package="com.sankuai.meituan", summary=one_item, xml=""
    ).ok
