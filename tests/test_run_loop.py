from pathlib import Path

from mano_android_use.run_loop import (
    TERMINAL_ERROR,
    TERMINAL_HUMAN,
    TERMINAL_OK,
    TERMINAL_STUCK,
    _action_fingerprint,
    android_run,
)


class _FakeSession:
    def __init__(self, *, awake: bool = True):
        self.run_id = "test-run"
        self.run_dir = Path("/tmp/mau-test-run")
        self.last_size = (1000, 1000)
        self.last_xml = "<hierarchy/>"
        self.last_package = "app.demo"
        self._events = []
        self._step = 0
        self._awake = awake

    def ensure_awake(self, *, auto_wake: bool = True):
        return {"awake": self._awake, "wakefulness": "Awake" if self._awake else "Asleep", "ok": True, "woke": False}

    def launch(self, package: str):
        return {"ok": True, "package": package}

    def observe(self, detail: str = "tree", max_nodes: int = 80):
        self._step += 1
        return {
            "step": self._step,
            "summary": "package=app.demo; labels=[设置]",
            "package": "app.demo",
            "safety": {"allow": True, "code": "OK", "reason": ""},
            "screenshot_path": "/tmp/missing.png",
        }

    def tap(self, x, y, semantic_hint: str = ""):
        return {"ok": True}

    def swipe(self, *a, **k):
        return {"ok": True}

    def type_text(self, text, semantic_hint: str = ""):
        return {"ok": True}

    def press(self, button):
        return {"ok": True}

    def log_event(self, row):
        self._events.append(row)


def test_empty_goal():
    res = android_run(_FakeSession(), "  ")
    assert res.status == TERMINAL_ERROR


def test_screen_off_need_human():
    res = android_run(_FakeSession(awake=False), "打开设置", max_steps=3)
    assert res.status == TERMINAL_HUMAN
    assert res.screen and res.screen.get("awake") is False
    assert res.tips


def test_action_fingerprint():
    fp = _action_fingerprint(
        {"action": "click"},
        {"pixel": [10, 20]},
    )
    assert fp == "click:[10, 20]:None"


def test_stuck_on_repeated_clicks(monkeypatch):
    session = _FakeSession()

    class _G:
        model = "fake"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            return GrounderResult(
                True,
                "fake",
                {"action": "click", "coordinate": [100, 100]},
                "{}",
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    monkeypatch.setattr(
        "mano_android_use.run_loop.pixel_from_normalized",
        lambda action, w, h: {"action": "click", "pixel": [100, 100]},
    )
    res = android_run(session, "open settings", max_steps=10, stuck_repeat=3)
    assert res.status == TERMINAL_STUCK
    assert res.steps == 3


def test_terminate_success(monkeypatch):
    session = _FakeSession()

    class _G:
        model = "fake"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            return GrounderResult(
                True,
                "fake",
                {"action": "terminate", "status": "success"},
                "{}",
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    res = android_run(session, "already done", max_steps=5)
    assert res.status == TERMINAL_OK


def test_system_button_press_alias(monkeypatch):
    session = _FakeSession()
    pressed = []

    def _press(button):
        pressed.append(button)
        return {"ok": True}

    session.press = _press  # type: ignore[method-assign]

    class _G:
        model = "fake"
        _n = 0

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            self._n += 1
            if self._n == 1:
                return GrounderResult(
                    True,
                    "fake",
                    {"action": "system_button_press", "button_name": "home"},
                    "{}",
                )
            return GrounderResult(
                True,
                "fake",
                {"action": "terminate", "status": "success"},
                "{}",
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    res = android_run(session, "go home then done", max_steps=5)
    assert pressed == ["home"]
    assert res.status == TERMINAL_OK