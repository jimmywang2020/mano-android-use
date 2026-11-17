from mano_android_use.safety import SafetyGateway, sanitize_semantic_hint


def test_blocks_payment_text():
    gw = SafetyGateway()
    d = gw.check_action({"action": "click"}, ui_blob="确认支付 ¥28")
    assert not d.allow
    assert d.code == "BLOCKED_BY_POLICY"


def test_allows_normal_tap():
    gw = SafetyGateway()
    d = gw.check_action({"action": "click"}, ui_blob="搜索 黄焖鸡", semantic_hint="open search")
    assert d.allow


def test_sanitize_strips_payment_phrases():
    out = sanitize_semantic_hint("加购双皮奶，不要立即支付，停在确认页")
    assert "立即支付" not in out
    assert "加购" in out or "双皮奶" in out or "确认" in out


def test_goal_payment_words_do_not_block_tap_on_safe_ui():
    """Goal hint with 立即支付 must not BLOCKED when the screen itself is safe."""
    gw = SafetyGateway()
    d = gw.check_action(
        {"action": "click"},
        ui_blob="外卖 搜索 双皮奶 加购",
        semantic_hint="美团外卖搜双皮奶加购；不要立即支付",
    )
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


def test_allows_coloros_settings_wallet_row():
    """Bare「支付」must not trip on Settings「钱包与支付」."""
    gw = SafetyGateway()
    d = gw.screen_looks_dangerous("云服务, 钱包与支付, 电池")
    assert d.allow
