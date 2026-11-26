from pathlib import Path

from mano_android_use.run_loop import screen_signature
from mano_android_use.tree import (
    compact_nodes,
    find_by_text,
    is_input_like,
    is_submit_control,
    label_index,
    looks_like_focus_query,
    resolve_tap_target,
    screen_digest_labels,
    summarize,
)

SAMPLE = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
    <node class="android.widget.EditText" text="搜索商家" clickable="true" bounds="[100,100][900,200]" resource-id="com.demo:id/search"/>
    <node class="android.widget.Button" text="提交订单" clickable="true" bounds="[100,2000][980,2200]"/>
    <node class="android.widget.TextView" text="黄焖鸡" clickable="false" bounds="[100,400][400,480]"/>
  </node>
</hierarchy>
"""

FIXTURES = Path(__file__).parent / "fixtures"


def test_compact_and_summary():
    nodes = compact_nodes(SAMPLE)
    assert any(n.get("text") == "搜索商家" for n in nodes)
    summary = summarize("com.demo", nodes)
    assert "com.demo" in summary
    assert "possible_payment_ui" in summary
    assert "has_text_field" in summary


def test_find():
    hits = find_by_text(SAMPLE, "黄焖")
    assert hits and hits[0]["text"] == "黄焖鸡"


def test_compact_skips_systemui():
    xml = (FIXTURES / "didi_fare_with_systemui.xml").read_text(encoding="utf-8")
    nodes = compact_nodes(xml, max_nodes=40, package="com.sdu.didi.psnger")
    blobs = " ".join(
        str(n.get("text") or n.get("desc") or "") for n in nodes
    )
    assert "微博通知" not in blobs
    assert "哔哩哔哩" not in blobs
    assert "一口价78.9元" in blobs
    assert "拼车" in blobs


def test_signature_distinguishes_home_vs_fare():
    home = (FIXTURES / "didi_home_with_systemui.xml").read_text(encoding="utf-8")
    fare = (FIXTURES / "didi_fare_with_systemui.xml").read_text(encoding="utf-8")
    pkg = "com.sdu.didi.psnger"
    # Dirty summaries that look alike (systemui-dominated) must still differ via tree fp.
    dirty = "package=com.sdu.didi.psnger; labels=[15:07, 微博通知：, 抖音通知：]"
    sig_home = screen_signature(package=pkg, summary=dirty, xml=home)
    sig_fare = screen_signature(package=pkg, summary=dirty, xml=fare)
    assert sig_home != sig_fare
    assert "一口价" in sig_fare or "78.9" in sig_fare
    assert "您想去哪里" in sig_home or "输入目的地" in sig_home


def test_compact_digest_misses_meituan_cart_bar_but_label_index_hits():
    """N0/N1: document-order digest drops bottom cart; label_index keeps it."""
    xml = (FIXTURES / "meituan_store_deep_header.xml").read_text(encoding="utf-8")
    pkg = "com.sankuai.meituan"
    digest = " ".join(
        screen_digest_labels(xml, package=pkg, max_labels=40, max_nodes=160)
    )
    assert "去结算" not in digest
    assert "已添加" not in digest
    assert find_by_text(xml, "去结算", package=pkg)

    idx = " ".join(
        label_index(
            xml,
            package=pkg,
            needles=["去结算", "已添加"],
        )
    )
    assert "去结算" in idx
    assert "已添加" in idx


def test_label_index_recovers_didi_unfinished_carpool():
    xml = (FIXTURES / "didi_fare_carpool_overlay.xml").read_text(encoding="utf-8")
    pkg = "com.sdu.didi.psnger"
    digest = " ".join(
        screen_digest_labels(xml, package=pkg, max_labels=40, max_nodes=160)
    )
    assert "未拼成" not in digest
    idx = " ".join(
        label_index(xml, package=pkg, needles=["未拼成", "一口价", "特价拼车"])
    )
    assert "未拼成" in idx
    assert "一口价" in idx


def test_resolve_tap_rejects_didi_daijiao_overlay():
    """特价拼车 must not resolve to operation_view / 代叫 strip."""
    xml = (FIXTURES / "didi_fare_carpool_overlay.xml").read_text(encoding="utf-8")
    pkg = "com.sdu.didi.psnger"
    hit = resolve_tap_target(xml, "特价拼车", package=pkg)
    assert hit is not None
    rid = str((hit.get("hit") or {}).get("resource_id") or "")
    desc = str((hit.get("hit") or {}).get("desc") or "")
    text = str((hit.get("hit") or {}).get("text") or "")
    assert "operation_view" not in rid
    assert "代叫" not in desc and "代叫" not in text
    # Center should sit in the car-row band, not the half-width 代叫 chip.
    assert 168 <= int(hit["x"]) <= 1056
    assert 2028 <= int(hit["y"]) <= 2185


def test_focus_query_helpers():
    assert looks_like_focus_query("搜索")
    assert looks_like_focus_query("请输入商品名")
    assert looks_like_focus_query("search")
    assert not looks_like_focus_query("加入购物车")
    assert not looks_like_focus_query("选规格")
    assert is_input_like({"class": "EditText", "text": "搜索商家"})
    assert is_input_like(
        {"class": "ViewGroup", "resource_id": "com.app:id/search_box", "text": None}
    )
    assert is_submit_control({"class": "Button", "text": "搜索"}, "搜索")
    assert not is_submit_control({"class": "Button", "text": "加入购物车"}, "加入购物车")


def test_resolve_tap_prefers_search_field_over_submit_button():
    """Hint「搜索」must focus the field, not press submit (default-term search)."""
    xml = (FIXTURES / "meituan_search_bar.xml").read_text(encoding="utf-8")
    pkg = "com.sankuai.meituan"
    hit = resolve_tap_target(xml, "搜索", package=pkg)
    assert hit is not None
    h = hit.get("hit") or {}
    cls = str(h.get("class") or "")
    text = str(h.get("text") or "")
    rid = str(h.get("resource_id") or "")
    assert text != "搜索" or cls != "Button"
    assert "search_btn" not in rid
    assert cls in {"EditText", "ViewGroup"} or "search" in rid.lower()
    # Field / bar center is left of the submit Button (~945).
    assert int(hit["x"]) < 880


def test_resolve_tap_button_first_still_prefers_edittext():
    """Even when Button「搜索」precedes EditText in document order."""
    xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" package="com.demo" bounds="[0,0][1080,2400]">
    <node class="android.widget.Button" text="搜索" clickable="true"
          bounds="[900,100][1000,180]" package="com.demo"/>
    <node class="android.widget.EditText" text="搜索商家" clickable="true"
          bounds="[100,100][880,180]" package="com.demo"
          resource-id="com.demo:id/search_edit"/>
  </node>
</hierarchy>
"""
    hit = resolve_tap_target(xml, "搜索", package="com.demo")
    assert hit is not None
    assert (hit.get("hit") or {}).get("class") == "EditText"
    assert int(hit["x"]) < 900


def test_resolve_tap_keeps_action_button():
    """Long action labels are not focus-routed away from their Button."""
    xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" package="com.demo" bounds="[0,0][1080,2400]">
    <node class="android.widget.EditText" text="搜索商家" clickable="true"
          bounds="[100,100][900,180]" package="com.demo"/>
    <node class="android.widget.Button" text="加入购物车" clickable="true"
          bounds="[100,2000][980,2200]" package="com.demo"/>
  </node>
</hierarchy>
"""
    hit = resolve_tap_target(xml, "加入购物车", package="com.demo")
    assert hit is not None
    assert (hit.get("hit") or {}).get("text") == "加入购物车"
    assert (hit.get("hit") or {}).get("class") == "Button"
