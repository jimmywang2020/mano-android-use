from mano_android_use.display import parse_wakefulness
from mano_android_use.tips import PLAYBOOK_LINES, build_tips


def test_parse_wakefulness():
    assert parse_wakefulness("foo\nmWakefulness=Awake\nbar") == "Awake"
    assert parse_wakefulness("mWakefulness=Asleep") == "Asleep"
    assert parse_wakefulness("") == "unknown"


def test_build_tips_ime_and_screen():
    tips = build_tips(
        screen={"awake": False},
        text_backend={"available": False, "reason": "missing"},
        include_playbook=True,
    )
    assert any("AdbKeyboard" in t for t in tips)
    assert any("asleep" in t.lower() or "off" in t.lower() for t in tips)
    assert PLAYBOOK_LINES[0] in tips
