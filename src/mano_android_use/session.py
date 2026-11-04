"""L0 DeviceSession: mano ADB observe/act/journal without requiring a Pack."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mano.adb_executor import Adb, execute_action, find_adb
from mano.errors import ManoError
from mano.media import png_size
from mano.observation import capture_observation
from mano.text_input import OpenAtxAdbKeyboardBackend

from .safety import SafetyDecision, SafetyGateway
from .tree import compact_nodes, find_by_text, summarize


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class DeviceSession:
    serial: str
    run_dir: Path
    adb: Adb
    safety: SafetyGateway = field(default_factory=SafetyGateway)
    step: int = 0
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_xml: str = ""
    last_package: str = ""
    last_size: tuple[int, int] = (0, 0)
    _journal: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def open(
        cls,
        serial: str | None = None,
        *,
        runs_root: Path | str | None = None,
        unicode_text: bool = True,
        safety: SafetyGateway | None = None,
    ) -> "DeviceSession":
        serial = serial or os.getenv("MANO_DEVICE_SERIAL", "").strip()
        if not serial:
            raise ManoError("MANO_DEVICE_SERIAL (or serial=) is required")
        # Touch adb early so doctor fails closed.
        find_adb()
        root = Path(runs_root or os.getenv("MAU_RUNS_DIR", "runs"))
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        run_dir = root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        text_backend = OpenAtxAdbKeyboardBackend() if unicode_text else None
        adb = Adb(serial, text_backend=text_backend)
        return cls(
            serial=serial,
            run_dir=run_dir,
            adb=adb,
            safety=safety or SafetyGateway(),
            run_id=run_id,
        )

    def doctor(self) -> dict[str, Any]:
        adb_bin = find_adb()
        try:
            state = self.adb.shell("getprop", "ro.build.version.release")
            fg = self.adb.foreground_package()
            ok = True
            err = ""
        except Exception as exc:  # noqa: BLE001 — surface to host
            state, fg, ok, err = "", "", False, str(exc)[:500]
        return {
            "ok": ok,
            "adb": adb_bin,
            "serial": self.serial,
            "android_release": state,
            "foreground": fg,
            "run_dir": str(self.run_dir),
            "run_id": self.run_id,
            "error": err or None,
        }

    def ready(self) -> dict[str, Any]:
        info = self.doctor()
        if not info["ok"]:
            info["ready"] = False
            return info
        # Optional unicode IME preflight — warn only.
        try:
            cap = self.adb.text_backend.preflight(self.adb)
            info["text_backend"] = {
                "name": cap.name,
                "available": cap.available,
                "unicode": cap.unicode,
                "reason": cap.reason,
            }
        except Exception as exc:  # noqa: BLE001
            info["text_backend"] = {"available": False, "reason": str(exc)[:300]}
        info["ready"] = True
        return info

    def _capture_frame(self, adb: Adb, path: Path) -> tuple[int, int]:
        return adb.screenshot(path)

    def observe(self, *, detail: str = "tree", max_nodes: int = 80) -> dict[str, Any]:
        """Observe device. detail: tree|screenshot|both (default tree = no host image)."""
        self.step += 1
        obs = capture_observation(
            self.adb,
            self.run_dir,
            self.step,
            capture_frame=self._capture_frame,
        )
        self.last_xml = obs.xml
        self.last_package = obs.foreground
        self.last_size = (obs.width, obs.height)
        nodes = compact_nodes(obs.xml, max_nodes=max_nodes)
        summary = summarize(obs.foreground, nodes)
        danger = self.safety.screen_looks_dangerous(
            " ".join(
                str(n.get("text") or n.get("desc") or "") for n in nodes
            )
        )
        payload: dict[str, Any] = {
            "step": self.step,
            "observation_id": obs.observation_id,
            "package": obs.foreground,
            "stability": obs.stability,
            "size": [obs.width, obs.height],
            "summary": summary,
            "tree_compact": nodes,
            "safety": danger.to_dict(),
            "screenshot_path": str(self.run_dir / obs.screenshot),
            "xml_path": str(self.run_dir / obs.xml_path),
        }
        if detail in {"screenshot", "both"}:
            # Host-facing: path only by default; raw base64 is expensive — expose path.
            payload["screenshot_for_host"] = True
            payload["note"] = (
                "Screenshot saved on disk for debugging; prefer propose_action "
                "for grounding instead of feeding PNG to the host model."
            )
        else:
            payload["screenshot_for_host"] = False
        self._log({"event": "observe", **{k: payload[k] for k in ("step", "package", "summary", "stability")}})
        return payload

    def find(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        if not self.last_xml:
            self.observe(detail="tree")
        hits = find_by_text(self.last_xml, query, limit=limit)
        return {"query": query, "count": len(hits), "hits": hits}

    def launch(self, package: str) -> dict[str, Any]:
        decision = self.safety.check_package(package)
        if not decision.allow:
            return {"ok": False, **decision.to_dict()}
        self.adb.cold_start(package)
        self._log({"event": "launch", "package": package})
        return {"ok": True, "package": package}

    def press(self, button: str) -> dict[str, Any]:
        action = {"action": "system_button", "button": button.upper()}
        return self._act(action, semantic_hint=button)

    def tap(self, x: int, y: int, *, semantic_hint: str = "") -> dict[str, Any]:
        self._refresh_ui_snapshot()
        action = {"action": "click", "coordinate": [x, y], "_pixel": True}
        return self._act_pixels(action, x, y, semantic_hint=semantic_hint)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        duration_ms: int = 700,
        semantic_hint: str = "",
    ) -> dict[str, Any]:
        self._refresh_ui_snapshot()
        action = {
            "action": "swipe",
            "coordinate": [x1, y1],
            "coordinate2": [x2, y2],
            "duration_ms": duration_ms,
            "_pixel": True,
        }
        decision = self.safety.check_action(
            action,
            package=self.last_package,
            ui_blob=self.last_xml,
            semantic_hint=semantic_hint,
        )
        if not decision.allow:
            self._log({"event": "swipe_blocked", **decision.to_dict()})
            return {"ok": False, **decision.to_dict()}
        self.adb.swipe(x1, y1, x2, y2, duration_ms=duration_ms)
        self._log({"event": "swipe", "from": [x1, y1], "to": [x2, y2]})
        return {"ok": True}

    def type_text(self, text: str, *, semantic_hint: str = "") -> dict[str, Any]:
        action = {"action": "type", "text": text}
        return self._act(action, semantic_hint=semantic_hint or text)

    def _refresh_ui_snapshot(self) -> None:
        """Fresh XML + package before safety. Needed because each CLI invoke is a new process."""
        try:
            self.last_package = self.adb.foreground_package()
            self.last_xml = self.adb.ui_dump().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            self._log({"event": "ui_refresh_error", "error": str(exc)[:300]})
        if self.last_size == (0, 0):
            shot = self.run_dir / f"size-{self.step or 0}.png"
            try:
                self.last_size = self.adb.screenshot(shot)
            except Exception as exc:  # noqa: BLE001
                self._log({"event": "size_refresh_error", "error": str(exc)[:300]})

    def _act(self, action: dict[str, Any], *, semantic_hint: str = "") -> dict[str, Any]:
        self._refresh_ui_snapshot()
        decision = self.safety.check_action(
            action,
            package=self.last_package,
            ui_blob=self.last_xml,
            semantic_hint=semantic_hint,
        )
        if not decision.allow:
            self._log({"event": "act_blocked", "action": action, **decision.to_dict()})
            return {"ok": False, **decision.to_dict()}
        w, h = self.last_size
        if w <= 0 or h <= 0:
            shot = self.run_dir / f"size-{self.step}.png"
            w, h = self.adb.screenshot(shot)
            self.last_size = (w, h)
        # Map pixel-less normalized actions: for type/key use as-is.
        try:
            if action.get("action") == "type":
                execute_action(self.adb, {"action": "type", "text": action.get("text", "")}, w, h)
            elif action.get("action") == "system_button":
                execute_action(
                    self.adb,
                    {"action": "system_button", "button": str(action.get("button", "BACK")).upper()},
                    w,
                    h,
                )
            elif action.get("action") == "key":
                execute_action(self.adb, action, w, h)
            else:
                execute_action(self.adb, action, w, h)
        except ManoError as exc:
            self._log({"event": "act_error", "error": str(exc)[:500]})
            return {"ok": False, "code": "ACT_ERROR", "reason": str(exc)[:500]}
        self._log({"event": "act", "action": {k: v for k, v in action.items() if not str(k).startswith("_")}})
        return {"ok": True}

    def _act_pixels(
        self,
        action: dict[str, Any],
        x: int,
        y: int,
        *,
        semantic_hint: str = "",
    ) -> dict[str, Any]:
        decision = self.safety.check_action(
            action,
            package=self.last_package,
            ui_blob=self.last_xml,
            semantic_hint=semantic_hint,
        )
        if not decision.allow:
            self._log({"event": "tap_blocked", "xy": [x, y], **decision.to_dict()})
            return {"ok": False, **decision.to_dict()}
        self.adb.tap(x, y)
        self._log({"event": "tap", "xy": [x, y], "hint": semantic_hint or None})
        return {"ok": True}

    def _log(self, row: dict[str, Any]) -> None:
        row = {"ts_ms": _now_ms(), "run_id": self.run_id, **row}
        self._journal.append(row)
        path = self.run_dir / "journal.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def journal_tail(self, n: int = 20) -> list[dict[str, Any]]:
        return self._journal[-n:]
