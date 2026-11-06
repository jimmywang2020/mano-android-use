from pathlib import Path

from mano_android_use.run_loop import TERMINAL_OK, TERMINAL_STUCK, android_run
from mano_android_use.success_check import SuccessCheck, evaluate_success


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


def test_summary_only_ignores_buried_xml_city():
    """Home feed XML may mention 北京; default check must not use full XML."""
    v = evaluate_success(
        SuccessCheck(
            package="ctrip.android.view",
            labels_all=["北京"],
            labels_any=["酒店"],
        ),
        package="ctrip.android.view",
        summary="package=ctrip.android.view; labels=[会员, 酒店, 攻略]",
        xml='<node text="北京精品游"/>',
    )
    assert not v.ok


def test_summary_only_ignores_buried_xml_city():
    """Home feed XML may mention 北京; default check must not use full XML."""
    v = evaluate_success(
        SuccessCheck(
            package="ctrip.android.view",
            labels_all=["北京"],
            labels_any=["酒店"],
        ),
        package="ctrip.android.view",
        summary="package=ctrip.android.view; labels=[会员, 酒店, 攻略]",
        xml='<node text="北京精品游"/>',
    )
    assert not v.ok


def test_early_stop_on_success_check(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")
        last_size = (100, 100)
        last_xml = "<node text='北京精品民宿'/>"
        last_package = "ctrip.android.view"

        def ensure_awake(self, *, auto_wake=True):
            return {"awake": True, "wakefulness": "Awake", "ok": True, "woke": False}

        def observe(self, detail="tree", max_nodes=80):
            return {
                "step": 1,
                "summary": "package=ctrip.android.view; labels=[北京, 民宿列表]",
                "package": "ctrip.android.view",
                "safety": {"allow": True, "code": "OK", "reason": ""},
                "screenshot_path": "/tmp/missing.png",
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


def test_terminate_vetoed_then_stuck(monkeypatch):
    class _S:
        run_id = "r"
        run_dir = Path("/tmp/mau")
        last_size = (100, 100)
        last_xml = "<hierarchy/>"
        last_package = "other.app"
        _step = 0

        def ensure_awake(self, *, auto_wake=True):
            return {"awake": True, "wakefulness": "Awake", "ok": True, "woke": False}

        def observe(self, detail="tree", max_nodes=80):
            self._step += 1
            return {
                "step": self._step,
                "summary": "package=other.app; labels=[首页]",
                "package": "other.app",
                "safety": {"allow": True, "code": "OK", "reason": ""},
                "screenshot_path": "/tmp/missing.png",
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
        success_check=SuccessCheck(package="ctrip.android.view", labels_any=["北京"]),
    )
    # vetoed each step → eventually BUDGET
    assert res.status in {"BUDGET_EXCEEDED", TERMINAL_STUCK}
    assert any(h.get("terminate_vetoed") for h in res.history)
