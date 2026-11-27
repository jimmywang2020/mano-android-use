"""Phase R: STUCK → Host L0 quota=1 then L0_BLOCKED_AFTER_STUCK."""

from __future__ import annotations

from pathlib import Path

from mano_android_use.apply_action import VIA_L0_DIRECT
from mano_android_use.orchestration_gate import CODE_L0_BLOCKED_AFTER_STUCK, STATUS_STUCK
from mano_android_use.session import DeviceSession


class _Adb:
    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []
        self.swipes = 0
        self.text_backend = None

    def foreground_package(self) -> str:
        return "com.demo"

    def ui_dump(self) -> bytes:
        return b"<hierarchy/>"

    def screenshot(self, path: Path) -> tuple[int, int]:
        path.write_bytes(b"")
        return (1080, 2400)

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, *a, **k) -> None:
        self.swipes += 1


def _session(tmp_path: Path) -> DeviceSession:
    return DeviceSession(
        serial="test",
        run_dir=tmp_path,
        adb=_Adb(),  # type: ignore[arg-type]
        run_id="t",
    )


def test_arm_only_on_stuck(tmp_path: Path):
    s = _session(tmp_path)
    s.note_android_run_terminal("TIME_BUDGET")
    assert not s._orch_gate_armed
    s.note_android_run_terminal(STATUS_STUCK)
    assert s._orch_gate_armed
    assert s._l0_after_stuck_remaining == 1


def test_android_run_stop_event_arms(tmp_path: Path):
    s = _session(tmp_path)
    s.log_event({"event": "android_run_stop", "status": STATUS_STUCK})
    assert s._orch_gate_armed
    assert s.last_run_status == STATUS_STUCK


def test_begin_disarms(tmp_path: Path):
    s = _session(tmp_path)
    s.arm_orchestration_gate_after_stuck()
    s.note_android_run_begin()
    assert not s._orch_gate_armed
    assert s._l0_after_stuck_remaining == 0


def test_quota_one_then_block(tmp_path: Path):
    s = _session(tmp_path)
    s.last_xml = "<hierarchy/>"
    s.last_size = (1080, 2400)
    s.arm_orchestration_gate_after_stuck()
    ok = s.tap(10, 20, via=VIA_L0_DIRECT)
    assert ok.get("ok") is True
    assert len(s.adb.taps) == 1  # type: ignore[attr-defined]
    denied = s.tap(11, 21, via=VIA_L0_DIRECT)
    assert denied.get("ok") is False
    assert denied.get("code") == CODE_L0_BLOCKED_AFTER_STUCK
    assert denied.get("next") == ["find", "slot_peek", "android_run"]
    assert len(s.adb.taps) == 1  # type: ignore[attr-defined]


def test_force_l0_after_quota(tmp_path: Path):
    s = _session(tmp_path)
    s.last_xml = "<hierarchy/>"
    s.last_size = (1080, 2400)
    s.arm_orchestration_gate_after_stuck()
    assert s.tap(1, 1, via=VIA_L0_DIRECT).get("ok") is True
    denied = s.tap(2, 2, via=VIA_L0_DIRECT)
    assert denied.get("code") == CODE_L0_BLOCKED_AFTER_STUCK
    forced = s.tap(3, 3, via=VIA_L0_DIRECT, force_l0=True)
    assert forced.get("ok") is True
    assert len(s.adb.taps) == 2  # type: ignore[attr-defined]


def test_android_run_via_not_gated(tmp_path: Path):
    s = _session(tmp_path)
    s.last_xml = "<hierarchy/>"
    s.last_size = (1080, 2400)
    s.arm_orchestration_gate_after_stuck()
    s._l0_after_stuck_remaining = 0
    ok = s.tap(5, 5, via="android_run")
    assert ok.get("ok") is True
    assert len(s.adb.taps) == 1  # type: ignore[attr-defined]


def test_goal_reached_disarms(tmp_path: Path):
    s = _session(tmp_path)
    s.arm_orchestration_gate_after_stuck()
    s.note_android_run_terminal("GOAL_REACHED")
    assert not s._orch_gate_armed
