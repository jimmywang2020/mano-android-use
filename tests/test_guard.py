"""Phase M2 ActClass + Guard."""

from __future__ import annotations

from pathlib import Path

from mano_android_use.act_class import (
    CONFIRM_ADD,
    OPEN_SPEC,
    UNKNOWN_TARGET,
    classify_act_class,
    classify_action,
    resolve_target_key,
)
from mano_android_use.guard import (
    CODE_DENY,
    CODE_NOOP,
    SKIP_GUARD_DENY,
    SKIP_GUARD_NOOP,
    filter_tree_candidates,
    guard_proposed_act,
)
from mano_android_use.run_loop import TERMINAL_OK, android_run


def test_classify_open_spec_and_confirm_add():
    assert classify_act_class(kind="click", hint="选规格") == OPEN_SPEC
    assert classify_act_class(kind="click", hint="加入购物车") == CONFIRM_ADD
    assert classify_act_class(kind="type", hint="柠檬茶") == "type_query"


def test_resolve_target_key_prefers_hint_then_unique_goal_sku():
    keys = ["鸭屎香柠檬茶", "冰美式"]
    assert resolve_target_key(hint="选规格 鸭屎香柠檬茶", sku_keys=keys) == "鸭屎香柠檬茶"
    assert resolve_target_key(hint="选规格", goal="加购冰美式", sku_keys=keys) == "冰美式"
    # Both skus in goal → unknown (no false idempotent)
    assert (
        resolve_target_key(hint="选规格", goal="汉堡和冰美式", sku_keys=["汉堡", "冰美式"])
        == UNKNOWN_TARGET
    )


def test_guard_noop_open_spec_when_sku_already_in_world():
    progress = {
        "world": {"cart_count": 1, "sku_keys": ["鸭屎香柠檬茶"]},
    }
    d = guard_proposed_act(
        progress=progress,
        kind="click",
        hint="选规格",
        goal="在店内为鸭屎香柠檬茶选规格加入购物车",
        action={"action": "click", "text": "选规格"},
    )
    assert d.code == CODE_NOOP
    assert d.skip_reason == SKIP_GUARD_NOOP
    assert d.act_class == OPEN_SPEC
    assert d.target_key == "鸭屎香柠檬茶"


def test_guard_unknown_target_no_false_idempotent():
    progress = {"world": {"sku_keys": ["汉堡"]}}
    d = guard_proposed_act(
        progress=progress,
        kind="click",
        hint="选规格",
        goal="加购冰美式",  # different SKU, not in world
        action={"action": "click", "text": "选规格"},
    )
    assert d.allow is True
    assert d.target_key == UNKNOWN_TARGET


def test_guard_banned_hint_and_act_class():
    progress = {
        "policy": {
            "banned_hint_labels": ["已添加", "去结算"],
            "banned_act_classes": ["open_spec"],
        }
    }
    d1 = guard_proposed_act(
        progress=progress,
        kind="click",
        hint="已添加",
        goal="确认购物车",
    )
    assert d1.code == CODE_DENY and d1.skip_reason == SKIP_GUARD_DENY

    d2 = guard_proposed_act(
        progress=progress,
        kind="click",
        hint="选规格",
        goal="随便",
    )
    assert d2.code == CODE_DENY
    assert d2.act_class == OPEN_SPEC

    assert filter_tree_candidates(
        ["选规格", "已添加", "去结算", "柠檬茶"],
        progress,
    ) == ["选规格", "柠檬茶"]


def test_tree_shortcut_guard_noop_skips_tap(monkeypatch, tmp_path: Path):
    """SKU already in cart + shortcut 选规格 → guard_noop, no device tap."""

    class _Session:
        def __init__(self) -> None:
            self.run_id = "g1"
            self.run_dir = tmp_path
            self.step = 0
            self.last_size = (1080, 2412)
            self.last_xml = "<hierarchy/>"
            self._taps: list[dict] = []
            self._events: list[dict] = []
            self._shot = tmp_path / "step-01.png"
            self._shot.write_bytes(b"png")

        def begin_run(self, **k):
            return {"run_id": self.run_id, "run_dir": str(self.run_dir)}

        def ensure_awake(self, *, auto_wake: bool = True):
            return {"awake": True, "wakefulness": "Awake", "ok": True, "woke": False}

        def ensure_package(self, *a, **k):
            return {"ok": True}

        def log_event(self, row):
            self._events.append(dict(row))

        def find(self, query, limit=10):
            return {
                "hits": [{"text": query, "center": [50, 50], "clickable": True}]
            }

        def tap(self, x, y, semantic_hint="", via=""):
            self._taps.append({"x": x, "y": y, "via": via})
            return {"ok": True, "via": via}

        def observe(self, detail="tree", max_nodes=80, bump_step=True, capture_mode=None):
            mode = capture_mode or "full"
            if bump_step:
                self.step += 1
            return {
                "step": self.step,
                "summary": "package=com.sankuai.meituan; labels=[选规格, 鸭屎香柠檬茶]",
                "package": "com.sankuai.meituan",
                "safety": {"allow": True, "code": "OK", "reason": ""},
                "screenshot_path": str(self._shot),
                "capture_mode": mode,
                "tree_compact": [{"text": "选规格"}, {"text": "鸭屎香柠檬茶"}, {"text": "x"}],
                "observe_breakdown": {
                    "capture_mode": mode,
                    "screenshot_ms": 1,
                    "xml_ms": 1,
                },
            }

        def press(self, *a, **k):
            return {"ok": True}

    session = _Session()
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

    res = android_run(
        session,  # type: ignore[arg-type]
        "为鸭屎香柠檬茶选规格加入购物车，不要支付",
        max_steps=4,
        tree_hints=["选规格"],
        stuck_same_summary=0,
        initial_progress={
            "world": {"cart_count": 1, "sku_keys": ["鸭屎香柠檬茶"]},
        },
        new_run=False,
    )
    assert res.status == TERMINAL_OK
    assert session._taps == []
    assert proposes["n"] >= 1  # Phase P3: same-step VLM after shortcut miss
    assert any(e.get("event") == "tree_shortcut_miss" for e in session._events)
    miss = [h for h in res.history if h.get("tree_shortcut_miss")]
    assert miss and miss[0].get("tree_shortcut_miss_reason") in {
        "guard_noop",
        "guard_deny",
    }


def test_classify_action_tuple():
    act, target = classify_action(
        {"action": "click", "text": "加入购物车"},
        hint="加入购物车",
        goal="加汉堡",
        sku_keys=["汉堡"],
    )
    assert act == CONFIRM_ADD
    assert target == "汉堡"
