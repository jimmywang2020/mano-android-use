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
