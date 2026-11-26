from pathlib import Path

from mano_android_use.run_loop import screen_signature
from mano_android_use.tree import (
    compact_nodes,
    find_by_text,
    label_index,
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
