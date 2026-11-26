"""Phase Q2: skip redundant ui_dump when observe XML is fresh."""

from __future__ import annotations

from pathlib import Path

import pytest

from mano_android_use import session as session_mod
from mano_android_use.session import DeviceSession


class _Adb:
    def __init__(self) -> None:
        self.dumps = 0
        self.fg_calls = 0
        self.text_backend = None

    def foreground_package(self) -> str:
        self.fg_calls += 1
        return "com.demo"

    def ui_dump(self) -> bytes:
        self.dumps += 1
        return b"<hierarchy/>"

    def screenshot(self, path: Path) -> tuple[int, int]:
        path.write_bytes(b"")
        return (1080, 2400)

    def tap(self, x: int, y: int) -> None:
        return None


def _session(tmp_path: Path) -> DeviceSession:
    return DeviceSession(
        serial="test",
        run_dir=tmp_path,
        adb=_Adb(),  # type: ignore[arg-type]
        run_id="t",
    )


def test_refresh_skips_dump_when_xml_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(session_mod.ENV_UI_REFRESH_MAX_AGE_MS, "8000")
    s = _session(tmp_path)
    s.last_xml = "<hierarchy><node text='ok'/></hierarchy>"
    s._last_xml_ms = session_mod._now_ms()
    s._refresh_ui_snapshot()
    assert s.adb.dumps == 0  # type: ignore[attr-defined]
    assert s.adb.fg_calls == 1  # type: ignore[attr-defined]
    assert any(e.get("event") == "ui_refresh_skipped" for e in s._journal)


def test_refresh_dumps_when_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(session_mod.ENV_UI_REFRESH_MAX_AGE_MS, "8000")
    s = _session(tmp_path)
    s.last_xml = "<hierarchy/>"
    s._last_xml_ms = session_mod._now_ms() - 20_000
    s._refresh_ui_snapshot()
    assert s.adb.dumps == 1  # type: ignore[attr-defined]


def test_refresh_force_always_dumps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(session_mod.ENV_UI_REFRESH_MAX_AGE_MS, "8000")
    s = _session(tmp_path)
    s.last_xml = "<hierarchy/>"
    s._last_xml_ms = session_mod._now_ms()
    s._refresh_ui_snapshot(force=True)
    assert s.adb.dumps == 1  # type: ignore[attr-defined]


def test_refresh_max_age_zero_always_dumps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(session_mod.ENV_UI_REFRESH_MAX_AGE_MS, "0")
    s = _session(tmp_path)
    s.last_xml = "<hierarchy/>"
    s._last_xml_ms = session_mod._now_ms()
    s._refresh_ui_snapshot()
    assert s.adb.dumps == 1  # type: ignore[attr-defined]
