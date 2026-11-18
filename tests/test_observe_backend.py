"""Optional U2 observe backend: env resolve, success path, ADB fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from mano_android_use.observe_backend import (
    ENV_OBSERVE_BACKEND,
    CaptureBundle,
    U2ObserveBackend,
    resolve_backend,
    u2_importable,
)
from mano_android_use.session import DeviceSession
from mano_android_use.tips import build_tips


def test_resolve_backend_default(monkeypatch):
    monkeypatch.delenv(ENV_OBSERVE_BACKEND, raising=False)
    assert resolve_backend() == "adb"
    monkeypatch.setenv(ENV_OBSERVE_BACKEND, "u2")
    assert resolve_backend() == "u2"
    monkeypatch.setenv(ENV_OBSERVE_BACKEND, "ADB")
    assert resolve_backend() == "adb"


def test_tips_warn_when_u2_requested_unavailable():
    tips = build_tips(
        observe_backend={
            "requested": "u2",
            "available": False,
            "reason": "agent down",
        },
        include_playbook=False,
    )
    assert any("MAU_OBSERVE_BACKEND=u2" in t for t in tips)
    assert any("fall back" in t.lower() for t in tips)


def test_u2_capture_writes_files(tmp_path: Path, monkeypatch):
    img = Image.new("RGB", (20, 30), color=(1, 2, 3))
    fake = MagicMock()
    fake.info = {"currentPackageName": "app.demo", "productName": "test"}
    fake.app_current.return_value = {"package": "app.demo"}
    fake.screenshot.return_value = img
    fake.dump_hierarchy.return_value = "<hierarchy><node text='ok'/></hierarchy>"

    backend = U2ObserveBackend("serial-test")
    monkeypatch.setattr(backend, "connect", lambda: fake)
    obs = backend.capture(tmp_path, 1, mode="full")
    assert isinstance(obs, CaptureBundle)
    assert obs.observe_backend == "u2"
    assert obs.capture_mode == "full"
    assert obs.capture_attempt == 1
    assert (tmp_path / "step-01.png").is_file()
    assert (tmp_path / "step-01.xml").is_file()
    assert obs.width == 20 and obs.height == 30
    assert "ok" in obs.xml
    assert obs.screenshot_ms >= 0 and obs.xml_ms >= 0


def test_session_observe_u2_success(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(ENV_OBSERVE_BACKEND, "u2")
    monkeypatch.setenv("MANO_DEVICE_SERIAL", "serial-test")

    img = Image.new("RGB", (10, 10), color=(9, 9, 9))
    fake_u2 = MagicMock()
    fake_u2.info = {"currentPackageName": "com.android.settings"}
    fake_u2.app_current.return_value = {"package": "com.android.settings"}
    fake_u2.screenshot.return_value = img
    fake_u2.dump_hierarchy.return_value = (
        "<hierarchy><node text='设置' bounds='[0,0][10,10]'/></hierarchy>"
    )

    adb = MagicMock()
    adb.text_backend = None
    session = DeviceSession(
        serial="serial-test",
        run_dir=tmp_path / "run",
        adb=adb,
        run_id="test",
    )
    session.run_dir.mkdir(parents=True, exist_ok=True)
    session._u2 = U2ObserveBackend("serial-test")
    monkeypatch.setattr(session._u2, "connect", lambda: fake_u2)

    out = session.observe(detail="both")
    assert out["observe_backend"] == "u2"
    assert out["capture_mode"] == "full"
    assert out["observe_breakdown"]["observe_backend"] == "u2"
    assert Path(out["screenshot_path"]).is_file()
    assert "设置" in (out.get("summary") or "")
    adb.screenshot.assert_not_called()


def test_session_observe_u2_falls_back_to_adb(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(ENV_OBSERVE_BACKEND, "u2")

    from mano.observation import Observation

    adb = MagicMock()
    adb.text_backend = None
    session = DeviceSession(
        serial="serial-test",
        run_dir=tmp_path / "run",
        adb=adb,
        run_id="test",
    )
    session.run_dir.mkdir(parents=True, exist_ok=True)

    failing = U2ObserveBackend("serial-test")

    def _boom(*_a, **_k):
        raise RuntimeError("agent dead")

    monkeypatch.setattr(failing, "capture", _boom)
    session._u2 = failing

    shot = session.run_dir / "step-01.png"
    shot.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def _fake_capture(adb_obj, run_dir, step, *, capture_frame, mode="full", fallback_size=None):
        return Observation(
            observation_id="adb1",
            step=step,
            screenshot="step-01.png",
            xml_path="step-01.xml",
            width=1,
            height=1,
            foreground="app.demo",
            foreground_before="app.demo",
            foreground_after="app.demo",
            xml="<hierarchy/>",
            xml_fingerprint="x",
            capture_started_at=1,
            capture_finished_at=2,
            foreground_before_at=1,
            screenshot_started_at=1,
            screenshot_finished_at=2,
            xml_started_at=1,
            xml_finished_at=2,
            foreground_after_at=2,
            skew_ms=1,
            capture_attempt=1,
            stability="stable",
            capture_mode=mode,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(
        "mano_android_use.session.capture_observation", _fake_capture
    )
    (session.run_dir / "step-01.xml").write_text("<hierarchy/>", encoding="utf-8")

    out = session.observe(detail="both")
    assert out["observe_backend"] == "u2_fallback_adb"
    assert out["observe_breakdown"]["observe_backend"] == "u2_fallback_adb"
    assert any(
        e.get("event") == "observe_backend_fallback" for e in session._journal
    )


def test_u2_importable_smoke():
    # CI may or may not have the extra; function must not raise.
    assert isinstance(u2_importable(), bool)


@pytest.mark.parametrize("mode", ["tree", "shot", "full"])
def test_u2_capture_modes(tmp_path: Path, monkeypatch, mode: str):
    img = Image.new("RGB", (8, 8), color=(0, 0, 0))
    fake = MagicMock()
    fake.info = {"currentPackageName": "p"}
    fake.app_current.return_value = {"package": "p"}
    fake.screenshot.return_value = img
    fake.dump_hierarchy.return_value = "<hierarchy/>"
    backend = U2ObserveBackend("s")
    monkeypatch.setattr(backend, "connect", lambda: fake)
    obs = backend.capture(tmp_path, 2, mode=mode)  # type: ignore[arg-type]
    assert obs.capture_mode == mode
    if mode == "tree":
        assert not obs.screenshot and obs.xml_path
        fake.screenshot.assert_not_called()
    elif mode == "shot":
        assert obs.screenshot and not obs.xml_path
        fake.dump_hierarchy.assert_not_called()
    else:
        assert obs.screenshot and obs.xml_path
