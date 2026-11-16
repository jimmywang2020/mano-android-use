from mano_android_use.apply_action import (
    VIA_ANDROID_RUN,
    VIA_PROPOSE_EXECUTE,
    apply_action,
    normalize_kind,
)


class _Sess:
    def __init__(self):
        self.calls = []

    def tap(self, x, y, semantic_hint="", via=None):
        self.calls.append(("tap", x, y, via))
        return {"ok": True, "via": via}

    def swipe(self, x1, y1, x2, y2, duration_ms=700, semantic_hint="", via=None):
        self.calls.append(("swipe", x1, y1, x2, y2, via))
        return {"ok": True, "via": via}

    def type_text(self, text, semantic_hint="", via=None):
        self.calls.append(("type", text, via))
        return {"ok": True, "via": via}

    def press(self, button, via=None):
        self.calls.append(("press", button, via))
        return {"ok": True, "via": via}


def test_normalize_system_button_press_alias():
    kind, action = normalize_kind(
        {"action": "system_button_press", "button_name": "BACK"}
    )
    assert kind == "system_button"
    assert action.get("button") == "BACK"


def test_apply_click_via_android_run():
    s = _Sess()
    out = apply_action(
        s,
        {"action": "click"},
        {"pixel": [10, 20]},
        semantic_hint="open",
        via=VIA_ANDROID_RUN,
    )
    assert out["ok"] and out["via"] == VIA_ANDROID_RUN
    assert s.calls == [("tap", 10, 20, VIA_ANDROID_RUN)]


def test_apply_press_alias():
    s = _Sess()
    out = apply_action(
        s,
        {"action": "system_button_press", "button_name": "HOME"},
        {},
        via=VIA_PROPOSE_EXECUTE,
    )
    assert out["ok"]
    assert s.calls == [("press", "HOME", VIA_PROPOSE_EXECUTE)]


def test_apply_unsupported():
    s = _Sess()
    out = apply_action(s, {"action": "fly"}, {}, via=VIA_ANDROID_RUN)
    assert out["ok"] is False
    assert out["code"] == "UNSUPPORTED"
