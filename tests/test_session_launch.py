"""Warm vs cold launch behaviour."""

from __future__ import annotations

from pathlib import Path

from mano_android_use.session import DeviceSession


class _Adb:
    def __init__(self, fg: str = "com.app"):
        self.fg = fg
        self.calls: list[tuple] = []
        self.text_backend = None

    def foreground_package(self) -> str:
        return self.fg

    def shell(self, *args):
        self.calls.append(("shell", args))
        return ""

    def cold_start(self, package: str) -> None:
        self.calls.append(("cold_start", package))


def _session(fg: str = "com.app") -> DeviceSession:
    adb = _Adb(fg=fg)
    return DeviceSession(
        serial="test",
        run_dir=Path("/tmp/mau-launch-test"),
        adb=adb,  # type: ignore[arg-type]
        run_id="t",
    )


def test_warm_skips_when_already_foreground(tmp_path: Path):
    s = _session(fg="com.target")
    s.run_dir = tmp_path
    out = s.launch("com.target", cold=False)
    assert out["mode"] == "already_foreground"
    assert s.adb.calls == []  # type: ignore[attr-defined]


def test_warm_monkey_without_force_stop(tmp_path: Path):
    s = _session(fg="com.other")
    s.run_dir = tmp_path
    out = s.launch("com.target", cold=False)
    assert out["mode"] == "warm"
    assert ("cold_start", "com.target") not in s.adb.calls  # type: ignore[attr-defined]
    assert any(c[0] == "shell" and "monkey" in c[1] for c in s.adb.calls)  # type: ignore[attr-defined]


def test_cold_force_stops(tmp_path: Path):
    s = _session(fg="com.target")
    s.run_dir = tmp_path
    out = s.launch("com.target", cold=True)
    assert out["mode"] == "cold"
    assert ("cold_start", "com.target") in s.adb.calls  # type: ignore[attr-defined]
