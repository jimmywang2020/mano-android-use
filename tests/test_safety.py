from mano_android_use.safety import SafetyGateway


def test_blocks_payment_text():
    gw = SafetyGateway()
    d = gw.check_action({"action": "click"}, ui_blob="确认支付 ¥28")
    assert not d.allow
    assert d.code == "BLOCKED_BY_POLICY"


def test_allows_normal_tap():
    gw = SafetyGateway()
    d = gw.check_action({"action": "click"}, ui_blob="搜索 黄焖鸡", semantic_hint="open search")
    assert d.allow


def test_package_allowlist():
    gw = SafetyGateway(package_allowlist={"com.ok"})
    assert not gw.check_package("com.other").allow
    assert gw.check_package("com.ok").allow


def test_need_human_on_dangerous_screen():
    gw = SafetyGateway()
    d = gw.screen_looks_dangerous("去支付")
    assert not d.allow
    assert d.code == "NEED_HUMAN"


def test_blocks_payment_deep_in_long_xml():
    """Act safety must see keywords beyond a short prefix (CLI refresh uses full dump)."""
    gw = SafetyGateway()
    padding = "x" * 5000
    blob = padding + "现在支付 ¥636.42 CNY" + padding
    d = gw.check_action({"action": "click"}, ui_blob=blob)
    assert not d.allow
    assert d.code == "BLOCKED_BY_POLICY"


def test_allows_back_on_payment_screen():
    gw = SafetyGateway()
    d = gw.check_action(
        {"action": "system_button", "button": "BACK"},
        ui_blob="现在支付 ¥1",
    )
    assert d.allow
