from pathlib import Path

from mano_android_use.run_loop import TERMINAL_OK, TERMINAL_STUCK, android_run, continue_hint_for_run
from mano_android_use.success_check import SuccessCheck, evaluate_success

FIXTURES = Path(__file__).parent / "fixtures"


def test_evaluate_package_and_labels():
    v = evaluate_success(
        SuccessCheck(package="ctrip.android.view", labels_any=["北京"], labels_all=["民宿"]),
        package="ctrip.android.view",
        summary="package=ctrip; labels=[北京, 民宿, ¥398]",
        xml="",
    )
    assert v.ok

    bad = evaluate_success(
        SuccessCheck(package="ctrip.android.view", labels_all=["北京", "民宿"]),
        package="ctrip.android.view",
        summary="labels=[酒店]",
        xml="",
    )
    assert not bad.ok
    assert any("北京" in r for r in bad.reasons)


def test_forbid_labels_blocks_search_sheet_false_complete():
    """Dest-name on 请输入终点 recommend list must not pass a gated check."""
    loose = evaluate_success(
        SuccessCheck(package="com.sdu.didi.psnger", labels_any=["香蜜湖"]),
        package="com.sdu.didi.psnger",
        summary="labels=[请输入终点, 香蜜湖, 为你推荐]",
        xml="",
    )
    assert loose.ok  # shows why fixture OR is dangerous

    gated = evaluate_success(
        SuccessCheck(
            package="com.sdu.didi.psnger",
            labels_any=["选路线", "一口价", "未拼成"],
            forbid_labels=["请输入终点"],
        ),
        package="com.sdu.didi.psnger",
        summary="labels=[请输入终点, 香蜜湖, 为你推荐]",
        xml="",
    )
    assert not gated.ok
    assert any("forbid_labels" in r for r in gated.reasons)

    fare = evaluate_success(
        SuccessCheck(
            package="com.sdu.didi.psnger",
            labels_all=["未拼成", "一口价"],
            forbid_labels=["请输入终点"],
        ),
        package="com.sdu.didi.psnger",
        summary="labels=[选路线, 未拼成 48.8元, 一口价 32.5 元, 特惠快车]",
        xml="",
    )
    assert fare.ok


def test_forbid_labels_from_mapping_aliases():
    check = SuccessCheck.from_mapping(
        {
            "package": "com.sdu.didi.psnger",
            "labels_any": ["选路线"],
            "require_absent": ["请输入终点"],
        }
    )
    assert check is not None
    assert check.forbid_labels == ["请输入终点"]
    assert "forbid_labels" in check.to_dict()


def test_summary_only_ignores_buried_xml_city():
    """Opt out of foreground tree: buried XML city must not trigger."""
    v = evaluate_success(
        SuccessCheck(
            package="ctrip.android.view",
            labels_all=["北京"],
            labels_any=["酒店"],
            use_foreground_tree=False,
        ),
        package="ctrip.android.view",
        summary="package=ctrip.android.view; labels=[会员, 酒店, 攻略]",
        xml='<hierarchy><node package="ctrip.android.view" text="北京精品游"/></hierarchy>',
    )
    assert not v.ok


def test_didi_fare_check_despite_dirty_summary():
    """U2/ColorOS: systemui-filled summary still finds 一口价 via foreground tree."""
    xml = (FIXTURES / "didi_fare_with_systemui.xml").read_text(encoding="utf-8")
    dirty = "package=com.sdu.didi.psnger; labels=[15:07, 微博通知：, 哔哩哔哩通知：, 抖音通知：]"
    v = evaluate_success(
        SuccessCheck(
            package="com.sdu.didi.psnger",
            labels_any=["一口价", "元", "价格详情"],
        ),
        package="com.sdu.didi.psnger",
        summary=dirty,
        xml=xml,
    )
    assert v.ok
    assert v.matched

    home = (FIXTURES / "didi_home_with_systemui.xml").read_text(encoding="utf-8")
    home_v = evaluate_success(
        SuccessCheck(
            package="com.sdu.didi.psnger",
            labels_any=["一口价", "价格详情"],
        ),
        package="com.sdu.didi.psnger",
        summary=dirty,
        xml=home,
    )
    assert not home_v.ok


def test_use_xml_still_available():
    v = evaluate_success(
        SuccessCheck(labels_any=["埋藏价"], use_xml=True, use_foreground_tree=False),
        package="x",
        summary="labels=[]",
        xml='<node text="埋藏价99"/>',
    )
    assert v.ok


def test_resume_spec_shape():
    hint = continue_hint_for_run(
        goal="查价",
        package="com.sdu.didi.psnger",
        last_summary="labels=[一口价]",
        status="TIME_BUDGET",
        progress={"fare_seen": True},
        screen_digest={"labels": ["一口价78.9元"]},
        tree_hints=["拼车"],
        success_check={"package": "com.sdu.didi.psnger", "labels_any": ["一口价"]},
    )
    assert hint["next_actor"] == "host"
    assert hint["do"]["omit_package"] is True
    assert hint["do"]["cold_start"] is False
    assert "HOME" in hint["dont"]
    assert hint["progress"]["fare_seen"] is True
    assert hint["action"] == "android_run"  # legacy


def test_resume_spec_done_on_goal_reached():
    hint = continue_hint_for_run(
        goal="查价",
        status="GOAL_REACHED",
        progress={"fare_seen": True},
        screen_digest={"labels": ["一口价"], "evidence_refs": {"xml": "/tmp/x.xml"}},
    )
    assert hint["next_actor"] == "done"
    assert "Goal reached" in hint["suggestion"]
    assert hint["progress"]["fare_seen"] is True


def test_early_stop_on_success_check(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")
        last_size = (100, 100)
        last_xml = "<node text='北京精品民宿'/>"
        last_package = "ctrip.android.view"

        def ensure_awake(self, *, auto_wake=True):
            return {"awake": True, "wakefulness": "Awake", "ok": True, "woke": False}

        def observe(
            self,
            detail="tree",
            max_nodes=80,
            bump_step=True,
            capture_mode=None,
        ):
            return {
                "step": 1,
                "summary": "package=ctrip.android.view; labels=[北京, 民宿列表]",
                "package": "ctrip.android.view",
                "safety": {"allow": True, "code": "OK", "reason": ""},
                "screenshot_path": "",
                "capture_mode": "tree",
                "tree_compact": [
                    {"text": "北京"},
                    {"text": "民宿列表"},
                    {"text": "筛选"},
                ],
            }

        def log_event(self, row):
            pass

    called = {"n": 0}

    class _G:
        model = "fake"

        def propose(self, *a, **k):
            called["n"] += 1
            raise AssertionError("should not propose when check already ok")

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    res = android_run(
        _S(),
        "搜北京民宿",
        max_steps=5,
        success_check=SuccessCheck(
            package="ctrip.android.view",
            labels_any=["北京"],
            labels_all=["民宿"],
        ),
    )
    assert res.status == TERMINAL_OK
    assert res.reason == "success_check satisfied"
    assert called["n"] == 0
    assert res.progress and res.progress.get("goal_matched")


def test_terminate_vetoed_then_stuck(monkeypatch, tmp_path: Path):
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"PNG")

    class _S:
        run_id = "r"
        run_dir = tmp_path
        last_size = (100, 100)
        last_xml = "<hierarchy/>"
        last_package = "other.app"
        _step = 0
        _shot = shot

        def ensure_awake(self, *, auto_wake=True):
            return {"awake": True, "wakefulness": "Awake", "ok": True, "woke": False}

        def observe(
            self,
            detail="tree",
            max_nodes=80,
            bump_step=True,
            capture_mode=None,
        ):
            mode = capture_mode or (
                "tree" if detail == "tree" else ("shot" if detail == "screenshot" else "full")
            )
            if bump_step:
                self._step += 1
            return {
                "step": self._step or 1,
                "summary": "package=other.app; labels=[首页]",
                "package": "other.app",
                "safety": {"allow": True, "code": "OK", "reason": ""},
                "screenshot_path": str(self._shot) if mode in {"full", "shot"} else "",
                "capture_mode": mode,
                "tree_compact": [
                    {"text": "首页"},
                    {"text": "我的"},
                    {"text": "更多"},
                ],
                "observe_breakdown": {"capture_mode": mode, "screenshot_ms": 0, "xml_ms": 1},
            }

        def log_event(self, row):
            pass

    class _G:
        model = "fake"

        def propose(self, image, instruction):
            from mano_android_use.grounder import GrounderResult

            # Always claim success; check should veto until budget/stuck
            return GrounderResult(
                True, "fake", {"action": "terminate", "status": "success"}, "{}"
            )

    monkeypatch.setattr("mano_android_use.run_loop.Grounder", lambda model=None: _G())
    res = android_run(
        _S(),
        "open ctrip",
        max_steps=3,
        stuck_same_summary=0,
        success_check=SuccessCheck(package="ctrip.android.view", labels_any=["北京"]),
    )
    # vetoed each step → eventually BUDGET
    assert res.status in {"BUDGET_EXCEEDED", TERMINAL_STUCK}
    assert any(h.get("terminate_vetoed") for h in res.history)
