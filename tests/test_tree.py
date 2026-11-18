from pathlib import Path

from mano_android_use.run_loop import screen_signature
from mano_android_use.tree import compact_nodes, find_by_text, summarize

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
