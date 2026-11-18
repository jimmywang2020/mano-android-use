"""Optional observe backends for DeviceSession (ADB default; U2 opt-in)."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from mano.media import png_size
from mano.observation import xml_fingerprint

BackendName = Literal["adb", "u2"]
CaptureMode = Literal["full", "tree", "shot"]

ENV_OBSERVE_BACKEND = "MAU_OBSERVE_BACKEND"


def resolve_backend(raw: str | None = None) -> BackendName:
    """Return requested backend from env (default ``adb``)."""
    value = (raw if raw is not None else os.getenv(ENV_OBSERVE_BACKEND, "")).strip().lower()
    if value in {"u2", "uiautomator2", "atx"}:
        return "u2"
    return "adb"


def u2_importable() -> bool:
    try:
        import uiautomator2  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass
class CaptureBundle:
    """Duck-compatible with the Observation fields ``DeviceSession.observe`` uses."""

    observation_id: str
    step: int
    screenshot: str
    xml_path: str
    width: int
    height: int
    foreground: str
    foreground_before: str
    foreground_after: str
    xml: str
    xml_fingerprint: str
    capture_started_at: int
    capture_finished_at: int
    foreground_before_at: int
    screenshot_started_at: int
    screenshot_finished_at: int
    xml_started_at: int
    xml_finished_at: int
    foreground_after_at: int
    skew_ms: int
    capture_attempt: int
    stability: str
    capture_mode: CaptureMode
    observe_backend: str = "u2"

    @property
    def screenshot_ms(self) -> int:
        if self.screenshot_started_at <= 0 or self.screenshot_finished_at <= 0:
            return 0
        return max(0, self.screenshot_finished_at - self.screenshot_started_at)

    @property
    def xml_ms(self) -> int:
        if self.xml_started_at <= 0 or self.xml_finished_at <= 0:
            return 0
        return max(0, self.xml_finished_at - self.xml_started_at)

    @property
    def screenshot_skipped(self) -> bool:
        return self.capture_mode == "tree"

    @property
    def xml_skipped(self) -> bool:
        return self.capture_mode == "shot"


class U2ObserveBackend:
    """uiautomator2 HTTP observe: screenshot + dump_hierarchy → run_dir files."""

    def __init__(self, serial: str):
        self.serial = serial
        self._device: Any | None = None

    def connect(self) -> Any:
        if self._device is not None:
            return self._device
        if not u2_importable():
            raise RuntimeError(
                "uiautomator2 not installed; run: uv sync --extra u2 "
                f"(or pip install 'uiautomator2>=3.2'); {ENV_OBSERVE_BACKEND}=u2"
            )
        import uiautomator2 as u2

        self._device = u2.connect(self.serial)
        # Touch once so missing agent fails here, not mid-capture.
        _ = self._device.info
        return self._device

    def ping(self) -> dict[str, Any]:
        """Health for ready(); never raises."""
        if not u2_importable():
            return {
                "requested": "u2",
                "available": False,
                "reason": "uiautomator2 package missing (uv sync --extra u2)",
            }
        try:
            d = self.connect()
            info = d.info or {}
            return {
                "requested": "u2",
                "available": True,
                "reason": "",
                "product": str(info.get("productName") or ""),
                "package": str(info.get("currentPackageName") or ""),
            }
        except Exception as exc:  # noqa: BLE001
            self._device = None
            return {
                "requested": "u2",
                "available": False,
                "reason": str(exc)[:300],
            }

    def capture(
        self,
        run_dir: Path,
        step: int,
        *,
        mode: CaptureMode = "full",
        fallback_size: tuple[int, int] | None = None,
    ) -> CaptureBundle:
        if mode not in {"full", "tree", "shot"}:
            mode = "full"
        want_shot = mode in {"full", "shot"}
        want_xml = mode in {"full", "tree"}
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        d = self.connect()
        t0 = _now_ms()
        fg_before = ""
        try:
            cur = d.app_current() or {}
            fg_before = str(cur.get("package") or "")
        except Exception:  # noqa: BLE001
            fg_before = str((d.info or {}).get("currentPackageName") or "")
        fg_before_at = _now_ms()

        shot_name = ""
        xml_name = ""
        width = height = 0
        if not want_shot and fallback_size is not None:
            width, height = int(fallback_size[0]), int(fallback_size[1])

        shot_started = shot_finished = 0
        if want_shot:
            shot_started = _now_ms()
            img = d.screenshot()
            shot_path = run_dir / f"step-{step:02d}.png"
            img.save(str(shot_path), format="PNG")
            shot_finished = _now_ms()
            shot_name = shot_path.name
            width, height = png_size(shot_path)

        xml = ""
        xml_started = xml_finished = 0
        if want_xml:
            xml_started = _now_ms()
            xml = d.dump_hierarchy() or ""
            xml_finished = _now_ms()
            xml_path = run_dir / f"step-{step:02d}.xml"
            xml_path.write_text(xml, encoding="utf-8")
            xml_name = xml_path.name

        fg_after = fg_before
        try:
            cur = d.app_current() or {}
            fg_after = str(cur.get("package") or fg_before)
        except Exception:  # noqa: BLE001
            pass
        fg_after_at = _now_ms()
        finished = _now_ms()
        skew = max(0, finished - t0)
        stable = fg_before == fg_after and bool(fg_after)
        return CaptureBundle(
            observation_id=uuid.uuid4().hex[:12],
            step=step,
            screenshot=shot_name,
            xml_path=xml_name,
            width=width,
            height=height,
            foreground=fg_after or fg_before,
            foreground_before=fg_before,
            foreground_after=fg_after,
            xml=xml,
            xml_fingerprint=xml_fingerprint(xml) if xml else "",
            capture_started_at=t0,
            capture_finished_at=finished,
            foreground_before_at=fg_before_at,
            screenshot_started_at=shot_started,
            screenshot_finished_at=shot_finished,
            xml_started_at=xml_started,
            xml_finished_at=xml_finished,
            foreground_after_at=fg_after_at,
            skew_ms=skew,
            capture_attempt=1,
            stability="stable" if stable else "unstable",
            capture_mode=mode,  # type: ignore[arg-type]
            observe_backend="u2",
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def probe_u2(serial: str) -> dict[str, Any]:
    """ready() helper when env requests u2."""
    return U2ObserveBackend(serial).ping()
