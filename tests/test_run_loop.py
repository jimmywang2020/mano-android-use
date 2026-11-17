import json
from pathlib import Path

from mano_android_use.run_loop import (
    TERMINAL_ERROR,
    TERMINAL_HUMAN,
    TERMINAL_OK,
    TERMINAL_STUCK,
    TERMINAL_TIME_BUDGET,
    _action_fingerprint,
    android_run,
    collect_tree_candidates,
    extract_quoted_labels,
    screen_signature,
)
from mano_android_use.trace_report import EVENT_STEP, load_step_spans, load_trace


class _FakeSession:
    def __init__(self, *, awake: bool = True, run_dir: Path | None = None):
        self.run_id = "test-run"
        self.run_dir = Path(run_dir) if run_dir else Path("/tmp/mau-test-run")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.last_size = (1000, 1000)
        self.last_xml = "<hierarchy/>"
        self.last_package = "app.demo"
        self._events = []
        self._step = 0
        self._awake = awake
        self._find_hits: list[dict] = []
        self._taps: list[dict] = []
        self._presses: list[dict] = []
        self._summary = "package=app.demo; labels=[设置]"
        self._package = "app.demo"

    def ensure_awake(self, *, auto_wake: bool = True):
        return {"awake": self._awake, "wakefulness": "Awake" if self._awake else "Asleep", "ok": True, "woke": False}

    def find(self, query, limit: int = 10):
        hits = []
        for h in self._find_hits:
            blob = " ".join(
                str(x)
                for x in (h.get("text"), h.get("desc"), h.get("resource_id"))
                if x
            )
            if query in blob:
                hits.append(h)
            if len(hits) >= limit:
                break
        return {"query": query, "count": len(hits), "hits": hits}

    def launch(self, package: str):
        return {"ok": True, "package": package}

    def observe(self, detail: str = "tree", max_nodes: int = 80):
        self._step += 1
        return {
            "step": self._step,
            "summary": self._summary,
            "package": self._package,
            "safety": {"allow": True, "code": "OK", "reason": ""},
            "screenshot_path": "/tmp/missing.png",
        }

    def tap(self, x, y, semantic_hint: str = "", via: str | None = None):
        self._taps.append({"x": x, "y": y, "via": via, "hint": semantic_hint})
        out = {"ok": True}
        if via:
            out["via"] = via
        return out

    def swipe(self, *a, **k):
        out = {"ok": True}
        if k.get("via"):
            out["via"] = k["via"]
        return out

    def type_text(self, text, semantic_hint: str = "", via: str | None = None):
        out = {"ok": True}
        if via:
            out["via"] = via
        return out

    def press(self, button, via: str | None = None):
        self._presses.append({"button": button, "via": via})
        out = {"ok": True}
        if via:
            out["via"] = via
        return out

    def log_event(self, row):
        self._events.append(row)
        path = self.run_dir / "journal.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"run_id": self.run_id, **row}, ensure_ascii=False) + "\n")


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
    res = android_run(
        session,
        "open settings",
        max_steps=10,
        stuck_repeat=3,
        stuck_same_summary=0,
    )
    assert res.status == TERMINAL_STUCK
    assert res.steps == 3


def test_stuck_on_unchanged_screen_skips_vlm(monkeypatch):
    session = _FakeSession()
    proposes = {"n": 0}

    class _G:
        model = "fake"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            proposes["n"] += 1
            return GrounderResult(
                True,
                "fake",
                {"action": "click", "coordinate": [proposes["n"], proposes["n"]]},
                "{}",
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    monkeypatch.setattr(
        "mano_android_use.run_loop.pixel_from_normalized",
        lambda action, w, h: {
            "action": "click",
            "pixel": list(action.get("coordinate") or [1, 1]),
        },
    )
    # First observe → VLM; then recover/wait; STUCK on 3rd unchanged (step 4).
    res = android_run(
        session, "noop", max_steps=10, stuck_repeat=99, stuck_same_summary=3
    )
    assert res.status == TERMINAL_STUCK
    assert res.steps == 4
    assert "unchanged screen" in res.reason
    assert proposes["n"] == 1
    assert any(e.get("vlm_skipped") for e in session._events)
    assert res.cost_report and res.cost_report.get("vlm_skipped", 0) >= 1
    assert session._presses and session._presses[0]["button"] == "BACK"
    assert res.continue_hint is not None


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


def test_step_timing_and_trace_json(monkeypatch, tmp_path: Path):
    session = _FakeSession(run_dir=tmp_path)

    class _G:
        model = "fake-model"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            return GrounderResult(
                True,
                "fake-model",
                {"action": "terminate", "status": "success"},
                "{}",
                prompt_tokens=12,
                completion_tokens=3,
                call_count=1,
                latency_ms=7,
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    res = android_run(session, "already done", max_steps=5)
    assert res.status == TERMINAL_OK
    assert res.history and "timing" in res.history[0]
    timing = res.history[0]["timing"]
    assert timing["event"] == EVENT_STEP
    assert timing["grounder_ms"] >= 0
    assert timing["observe_ms"] >= 0
    assert timing["act_ms"] == 0
    assert timing["prompt_tokens"] == 12
    assert timing["completion_tokens"] == 3
    assert timing["action"] == "terminate"
    assert res.trace_summary is not None
    assert res.trace_summary["steps"] >= 1
    assert res.cost_report is not None
    assert "narrative" in res.cost_report
    assert res.cost_report["prompt_tokens"] == 12
    assert res.cost_report["by_phase"]["grounder"]["prompt_tokens"] == 12
    assert "Dominant:" in res.cost_report["narrative"]
    assert (tmp_path / "trace.json").is_file()
    assert any(e.get("event") == EVENT_STEP for e in session._events)
    spans = load_step_spans(tmp_path)
    assert len(spans) >= 1
    doc = load_trace(tmp_path)
    assert doc["totals"]["prompt_tokens"] == 12


def test_wall_budget_returns_time_budget(monkeypatch, tmp_path: Path):
    session = _FakeSession(run_dir=tmp_path)
    real_observe = session.observe

    def _slow_observe(detail: str = "tree", max_nodes: int = 80):
        import time

        time.sleep(0.05)
        return real_observe(detail=detail, max_nodes=max_nodes)

    session.observe = _slow_observe  # type: ignore[method-assign]

    class _G:
        model = "fake"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            return GrounderResult(
                True,
                "fake",
                {"action": "click", "coordinate": [1, 1]},
                "{}",
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    monkeypatch.setattr(
        "mano_android_use.run_loop.pixel_from_normalized",
        lambda action, w, h: {"action": "click", "pixel": [1, 1]},
    )
    res = android_run(
        session,
        "slow goal",
        max_steps=10,
        wall_budget_ms=1,
        stuck_repeat=99,
        stuck_same_summary=0,
    )
    assert res.status == TERMINAL_TIME_BUDGET
    assert "wall_budget_ms" in res.reason
    assert res.cost_report is not None
    assert "narrative" in res.cost_report
    assert res.continue_hint is not None
    assert res.continue_hint.get("action") == "android_run"
    assert res.continue_hint.get("recommended_max_steps") == 8


def test_system_button_press_alias(monkeypatch):
    session = _FakeSession()
    pressed = []

    def _press(button, via=None):
        pressed.append(button)
        return {"ok": True, "via": via}

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
    res = android_run(
        session, "go home then done", max_steps=5, stuck_same_summary=0
    )
    assert pressed == ["home"]
    assert res.status == TERMINAL_OK


def test_quoted_labels_and_screen_signature():
    assert extract_quoted_labels('打开「设置」然后点"蓝牙"') == ["设置", "蓝牙"]
    assert collect_tree_candidates('打开「设置」', ["蓝牙"]) == ["蓝牙", "设置"]
    sig_a = screen_signature(package="a", summary="package=a; labels=[x]")
    sig_b = screen_signature(package="a", summary="package=a; labels=[x]")
    assert sig_a == sig_b
    assert screen_signature(package="a", summary="package=a; labels=[y]") != sig_a


def test_tree_shortcut_skips_grounder(monkeypatch, tmp_path: Path):
    session = _FakeSession(run_dir=tmp_path)
    session._find_hits = [
        {"text": "设置", "center": [120, 340], "clickable": True},
    ]
    proposes = {"n": 0}

    class _G:
        model = "fake"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            proposes["n"] += 1
            return GrounderResult(
                True,
                "fake",
                {"action": "terminate", "status": "success"},
                "{}",
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())

    # After tree tap, change summary so unchanged path does not fire; then terminate.
    summaries = [
        "package=app.demo; labels=[设置]",
        "package=com.android.settings; labels=[设置, 搜索]",
    ]

    def _obs(detail: str = "tree", max_nodes: int = 80):
        session._step += 1
        session._summary = summaries[min(session._step - 1, len(summaries) - 1)]
        session._package = (
            "com.android.settings" if session._step > 1 else "app.demo"
        )
        return {
            "step": session._step,
            "summary": session._summary,
            "package": session._package,
            "safety": {"allow": True, "code": "OK", "reason": ""},
            "screenshot_path": "/tmp/missing.png",
        }

    session.observe = _obs  # type: ignore[method-assign]

    res = android_run(
        session,
        '打开「设置」',
        max_steps=5,
        tree_hints=["设置"],
        stuck_same_summary=0,
    )
    assert res.status == TERMINAL_OK
    assert proposes["n"] == 1  # only terminate step uses VLM
    assert session._taps and session._taps[0]["via"] == "tree_shortcut"
    assert session._taps[0]["x"] == 120
    assert any(
        e.get("via") == "tree_shortcut" and e.get("vlm_skipped") for e in session._events
    )
    assert res.cost_report and "tree_shortcut" in (res.cost_report.get("by_via") or {})


def test_tree_shortcut_multi_hit_falls_through_to_vlm(monkeypatch):
    session = _FakeSession()
    session._find_hits = [
        {"text": "设置", "center": [10, 10]},
        {"text": "设置", "center": [20, 20]},
    ]

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
    res = android_run(
        session, "打开设置", max_steps=3, tree_hints=["设置"], stuck_same_summary=0
    )
    assert res.status == TERMINAL_OK
    assert session._taps == []
