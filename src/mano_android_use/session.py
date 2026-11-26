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

from .apply_action import VIA_L0_DIRECT
from .display import ensure_awake, screen_state
from .observe_backend import (
    ENV_OBSERVE_BACKEND,
    U2ObserveBackend,
    probe_u2,
    resolve_backend,
)
from .safety import SafetyDecision, SafetyGateway
from .tips import build_tips
from .trace_report import EVENT_L0_STEP, build_step_span
from .tree import compact_nodes, find_by_text, summarize

# Phase Q2: skip redundant ui_dump before act when observe XML is still fresh.
# Wireless ADB often OOMs (exit 137) on a second dump seconds after full observe.
ENV_UI_REFRESH_MAX_AGE_MS = "MAU_UI_REFRESH_MAX_AGE_MS"
_DEFAULT_UI_REFRESH_MAX_AGE_MS = 8000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ui_refresh_max_age_ms() -> int:
    raw = (os.getenv(ENV_UI_REFRESH_MAX_AGE_MS) or "").strip()
    if not raw:
        return _DEFAULT_UI_REFRESH_MAX_AGE_MS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_UI_REFRESH_MAX_AGE_MS


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
    _u2: U2ObserveBackend | None = field(default=None, repr=False)
    _last_xml_ms: int = 0

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

    def begin_run(self, *, runs_root: Path | str | None = None) -> dict[str, Any]:
        """Open a fresh run_id/run_dir for the next android_run / plan.

        Keeps the ADB connection, safety gateway, and last observe cache so a
        warm resume does not force-stop the app. Prevents Host cost_report from
        accumulating prior MCP tasks that shared one long-lived session.
        """
        root = Path(runs_root) if runs_root is not None else self.run_dir.parent
        root.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        run_dir = root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.run_dir = run_dir
        self.step = 0
        self._journal = []
        self.log_event({"event": "begin_run", "run_id": run_id, "run_dir": str(run_dir)})
        return {"run_id": run_id, "run_dir": str(run_dir)}

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

    def screen(self) -> dict[str, Any]:
        """Current display wakefulness (Consumer preflight)."""
        return screen_state(self.adb)

    def ensure_awake(self, *, auto_wake: bool = True) -> dict[str, Any]:
        """Wake once with KEYCODE_WAKEUP if asleep; does not unlock keyguard."""
        return ensure_awake(self.adb, auto_wake=auto_wake)

    def ready(self) -> dict[str, Any]:
        info = self.doctor()
        if not info["ok"]:
            info["ready"] = False
            info["tips"] = build_tips(include_playbook=True)
            return info
        info["screen"] = self.screen()
        # Optional unicode IME preflight — warn only.
        try:
            if self.adb.text_backend is None:
                info["text_backend"] = {
                    "available": False,
                    "unicode": False,
                    "reason": "unicode_text disabled for this session",
                }
            else:
                cap = self.adb.text_backend.preflight(self.adb)
                info["text_backend"] = {
                    "name": cap.name,
                    "available": cap.available,
                    "unicode": cap.unicode,
                    "reason": cap.reason,
                }
        except Exception as exc:  # noqa: BLE001
            info["text_backend"] = {"available": False, "reason": str(exc)[:300]}
        requested = resolve_backend()
        info["observe_backend"] = {"requested": requested, "available": True, "reason": ""}
        if requested == "u2":
            info["observe_backend"] = probe_u2(self.serial)
        info["tips"] = build_tips(
            screen=info.get("screen"),
            text_backend=info.get("text_backend"),
            observe_backend=info.get("observe_backend"),
            include_playbook=True,
        )
        # Device reachable counts as ready; IME/screen issues are tips, not hard fail.
        info["ready"] = True
        return info

    def _u2_backend(self) -> U2ObserveBackend:
        if self._u2 is None:
            self._u2 = U2ObserveBackend(self.serial)
        return self._u2

    def _capture_frame(self, adb: Adb, path: Path) -> tuple[int, int]:
        return adb.screenshot(path)

    @staticmethod
    def capture_mode_for_detail(detail: str) -> str:
        """Map host-facing detail to Core capture_observation mode."""
        d = (detail or "tree").strip().lower()
        if d == "tree":
            return "tree"
        if d == "screenshot":
            return "shot"
        return "full"  # both / unknown → full

    def observe(
        self,
        *,
        detail: str = "tree",
        max_nodes: int = 80,
        bump_step: bool = True,
        capture_mode: str | None = None,
    ) -> dict[str, Any]:
        """Observe device.

        ``detail`` controls host payload *and* (unless ``capture_mode`` is set)
        Core capture cost: ``tree`` → dump only, ``screenshot`` → PNG only,
        ``both`` → full. Pass ``bump_step=False`` when upgrading the same logical
        step (e.g. tree gate then shot/full before VLM).
        """
        mode = (capture_mode or self.capture_mode_for_detail(detail)).strip().lower()
        if mode not in {"full", "tree", "shot"}:
            mode = "full"
        if bump_step:
            self.step += 1
        elif self.step <= 0:
            self.step = 1
        fallback = self.last_size if self.last_size[0] > 0 and self.last_size[1] > 0 else None
        requested = resolve_backend()
        observe_backend = "adb"
        u2_error = ""

        def _capture_adb(m: str):
            return capture_observation(
                self.adb,
                self.run_dir,
                self.step,
                capture_frame=self._capture_frame,
                mode=m,  # type: ignore[arg-type]
                fallback_size=fallback,
            )

        degrade_from = ""
        obs: Any = None
        if requested == "u2":
            try:
                obs = self._u2_backend().capture(
                    self.run_dir,
                    self.step,
                    mode=mode,  # type: ignore[arg-type]
                    fallback_size=fallback,
                )
                observe_backend = "u2"
            except Exception as exc:  # noqa: BLE001 — always allow ADB fallback
                u2_error = str(exc)[:300]
                self._u2 = None
                self._log(
                    {
                        "event": "observe_backend_fallback",
                        "from_backend": "u2",
                        "to_backend": "adb",
                        "error": u2_error,
                        "env": ENV_OBSERVE_BACKEND,
                    }
                )
                observe_backend = "u2_fallback_adb"

        if obs is None:
            try:
                obs = _capture_adb(mode)
            except Exception as exc:  # noqa: BLE001 — dump spikes / OOM must fail fast or degrade
                err = str(exc)[:300]
                code = str(getattr(exc, "code", "") or "")
                # tree dump failed → shot (skip gate); full dump failed → shot then re-raise.
                if mode == "tree":
                    degrade_from = "tree"
                    self._log(
                        {
                            "event": "observe_degrade",
                            "from_mode": "tree",
                            "to_mode": "shot",
                            "error": err,
                            "code": code,
                        }
                    )
                    try:
                        obs = _capture_adb("shot")
                    except Exception as exc2:  # noqa: BLE001
                        raise ManoError(
                            f"observe dump failed (tree→shot): {exc2}"
                        ) from exc2
                elif mode == "full":
                    degrade_from = "full"
                    self._log(
                        {
                            "event": "observe_degrade",
                            "from_mode": "full",
                            "to_mode": "shot",
                            "error": err,
                            "code": code,
                        }
                    )
                    try:
                        obs = _capture_adb("shot")
                    except Exception as exc2:  # noqa: BLE001
                        raise ManoError(
                            f"observe dump failed (full→shot): {exc2}"
                        ) from exc2
                else:
                    raise ManoError(f"observe failed ({mode}): {err}") from exc
            if observe_backend != "u2_fallback_adb":
                observe_backend = "adb"

        # Partial modes must not wipe the other modality's last_* cache.
        if obs.xml:
            self.last_xml = obs.xml
            self._last_xml_ms = _now_ms()
        if obs.foreground:
            self.last_package = obs.foreground
        if obs.width > 0 and obs.height > 0:
            self.last_size = (obs.width, obs.height)
        xml_for_tree = obs.xml if obs.xml else self.last_xml
        package = obs.foreground or self.last_package
        nodes = (
            compact_nodes(xml_for_tree, max_nodes=max_nodes, package=package)
            if xml_for_tree
            else []
        )
        summary = summarize(package, nodes)
        danger = self.safety.screen_looks_dangerous(
            " ".join(
                str(n.get("text") or n.get("desc") or "") for n in nodes
            )
        )
        shot_path = str(self.run_dir / obs.screenshot) if obs.screenshot else ""
        xml_path = str(self.run_dir / obs.xml_path) if obs.xml_path else ""
        breakdown = {
            "capture_mode": obs.capture_mode,
            "screenshot_ms": int(obs.screenshot_ms),
            "xml_ms": int(obs.xml_ms),
            "skew_ms": int(obs.skew_ms),
            "capture_attempt": int(obs.capture_attempt),
            "screenshot_skipped": bool(obs.screenshot_skipped),
            "xml_skipped": bool(obs.xml_skipped),
            "observe_backend": observe_backend,
        }
        if degrade_from:
            breakdown["degraded_from"] = degrade_from
        if u2_error:
            breakdown["u2_error"] = u2_error
        payload: dict[str, Any] = {
            "step": self.step,
            "observation_id": obs.observation_id,
            "package": package,
            "stability": obs.stability,
            "size": [self.last_size[0], self.last_size[1]],
            "summary": summary,
            "tree_compact": nodes,
            "safety": danger.to_dict(),
            "screenshot_path": shot_path,
            "xml_path": xml_path,
            "capture_mode": obs.capture_mode,
            "observe_backend": observe_backend,
            "observe_breakdown": breakdown,
        }
        if detail in {"screenshot", "both"} or mode in {"shot", "full"}:
            # Host-facing: path only by default; raw base64 is expensive — expose path.
            payload["screenshot_for_host"] = bool(shot_path)
            if shot_path:
                payload["note"] = (
                    "Screenshot saved on disk for debugging; prefer android_run "
                    "(or propose_action for one-shot debug) instead of feeding PNG to the host model."
                )
        else:
            payload["screenshot_for_host"] = False
        self._log(
            {
                "event": "observe",
                "step": payload["step"],
                "package": payload["package"],
                "summary": payload["summary"],
                "stability": payload["stability"],
                **breakdown,
            }
        )
        return payload

    def find(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        if not self.last_xml:
            self.observe(detail="tree")
        hits = find_by_text(
            self.last_xml,
            query,
            limit=limit,
            package=self.last_package or None,
        )
        return {"query": query, "count": len(hits), "hits": hits}

    def launch(self, package: str, *, cold: bool = False) -> dict[str, Any]:
        """Bring ``package`` to foreground.

        Default ``cold=False`` (warm): if already foreground, no-op; otherwise
        launcher intent without ``force-stop``. Pass ``cold=True`` only when a
        true relaunch is required (force-stop + start).
        """
        decision = self.safety.check_package(package)
        if not decision.allow:
            return {"ok": False, **decision.to_dict()}
        pkg = (package or "").strip()
        if not cold:
            try:
                fg = self.adb.foreground_package()
            except Exception:  # noqa: BLE001
                fg = ""
            if fg == pkg:
                self._log(
                    {
                        "event": "launch",
                        "package": pkg,
                        "mode": "already_foreground",
                        "cold": False,
                    }
                )
                return {"ok": True, "package": pkg, "mode": "already_foreground"}
            # Warm bring-to-front: prefer Core warm_start when available.
            warm = getattr(self.adb, "warm_start", None)
            if callable(warm):
                warm(pkg)
            else:
                self.adb.shell(
                    "monkey",
                    "-p",
                    pkg,
                    "-c",
                    "android.intent.category.LAUNCHER",
                    "1",
                )
                time.sleep(1.5)
            self._log({"event": "launch", "package": pkg, "mode": "warm", "cold": False})
            return {"ok": True, "package": pkg, "mode": "warm"}
        self.adb.cold_start(pkg)
        self._log({"event": "launch", "package": pkg, "mode": "cold", "cold": True})
        return {"ok": True, "package": pkg, "mode": "cold"}

    def _log_l0_span_if_direct(self, *, action: str, act_ms: int, via: str | None) -> None:
        """Bypass timing span for direct L0 only (not android_run / propose_execute)."""
        if via != VIA_L0_DIRECT:
            return
        span = build_step_span(
            step=self.step,
            model="",
            observe_ms=0,
            grounder_ms=0,
            act_ms=max(0, int(act_ms)),
            action=action,
            via=VIA_L0_DIRECT,
            event=EVENT_L0_STEP,
        )
        self._log(span)

    def press(self, button: str, *, via: str | None = None) -> dict[str, Any]:
        action = {"action": "system_button", "button": button.upper()}
        return self._act(action, semantic_hint=button, via=via)

    def tap(self, x: int, y: int, *, semantic_hint: str = "", via: str | None = None) -> dict[str, Any]:
        self._refresh_ui_snapshot()
        action = {"action": "click", "coordinate": [x, y], "_pixel": True}
        return self._act_pixels(action, x, y, semantic_hint=semantic_hint, via=via)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        duration_ms: int = 700,
        semantic_hint: str = "",
        via: str | None = None,
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
            row = {"event": "swipe_blocked", **decision.to_dict()}
            if via:
                row["via"] = via
            self._log(row)
            out = {"ok": False, **decision.to_dict()}
            if via:
                out["via"] = via
            return out
        t0 = time.perf_counter()
        self.adb.swipe(x1, y1, x2, y2, duration_ms=duration_ms)
        act_ms = int((time.perf_counter() - t0) * 1000)
        row = {"event": "swipe", "from": [x1, y1], "to": [x2, y2], "act_ms": act_ms}
        if via:
            row["via"] = via
        self._log(row)
        self._log_l0_span_if_direct(action="swipe", act_ms=act_ms, via=via)
        out: dict[str, Any] = {"ok": True, "act_ms": act_ms}
        if via:
            out["via"] = via
        return out

    def type_text(self, text: str, *, semantic_hint: str = "", via: str | None = None) -> dict[str, Any]:
        action = {"action": "type", "text": text}
        return self._act(action, semantic_hint=semantic_hint or text, via=via)

    def _refresh_ui_snapshot(self, *, force: bool = False) -> None:
        """XML + package before safety.

        Phase Q2: if ``last_xml`` from a recent observe is still within
        ``MAU_UI_REFRESH_MAX_AGE_MS`` (default 8s), skip ``ui_dump`` — a second
        dump on wireless ADB often exits 137 and burns 10–14s while keeping the
        old XML anyway. Package is still refreshed (cheap). Set force=True or
        max-age 0 to always dump.
        """
        max_age = _ui_refresh_max_age_ms()
        age = (_now_ms() - self._last_xml_ms) if self._last_xml_ms else None
        reuse = (
            not force
            and max_age > 0
            and bool(self.last_xml.strip())
            and age is not None
            and age <= max_age
        )
        try:
            self.last_package = self.adb.foreground_package()
        except Exception as exc:  # noqa: BLE001
            self._log(
                {"event": "ui_refresh_error", "error": ("foreground: " + str(exc))[:300]}
            )
        if reuse:
            self._log(
                {
                    "event": "ui_refresh_skipped",
                    "reason": "fresh_xml",
                    "age_ms": age,
                    "max_age_ms": max_age,
                }
            )
        else:
            try:
                self.last_xml = self.adb.ui_dump().decode("utf-8", errors="replace")
                self._last_xml_ms = _now_ms()
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "code", None) or ""
                self._log(
                    {
                        "event": "ui_refresh_error",
                        "error": str(exc)[:300],
                        "code": str(code) if code else None,
                        "kept_prior_xml": bool(self.last_xml.strip()),
                    }
                )
        if self.last_size == (0, 0):
            shot = self.run_dir / f"size-{self.step or 0}.png"
            try:
                self.last_size = self.adb.screenshot(shot)
            except Exception as exc:  # noqa: BLE001
                self._log({"event": "size_refresh_error", "error": str(exc)[:300]})

    def _act(
        self, action: dict[str, Any], *, semantic_hint: str = "", via: str | None = None
    ) -> dict[str, Any]:
        self._refresh_ui_snapshot()
        decision = self.safety.check_action(
            action,
            package=self.last_package,
            ui_blob=self.last_xml,
            semantic_hint=semantic_hint,
        )
        if not decision.allow:
            row = {"event": "act_blocked", "action": action, **decision.to_dict()}
            if via:
                row["via"] = via
            self._log(row)
            out = {"ok": False, **decision.to_dict()}
            if via:
                out["via"] = via
            return out
        w, h = self.last_size
        if w <= 0 or h <= 0:
            shot = self.run_dir / f"size-{self.step}.png"
            w, h = self.adb.screenshot(shot)
            self.last_size = (w, h)
        # Map pixel-less normalized actions: for type/key use as-is.
        t0 = time.perf_counter()
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
            act_ms = int((time.perf_counter() - t0) * 1000)
            row = {"event": "act_error", "error": str(exc)[:500], "act_ms": act_ms}
            if via:
                row["via"] = via
            self._log(row)
            out = {"ok": False, "code": "ACT_ERROR", "reason": str(exc)[:500], "act_ms": act_ms}
            if via:
                out["via"] = via
            return out
        act_ms = int((time.perf_counter() - t0) * 1000)
        kind = str(action.get("action") or "act")
        row = {
            "event": "act",
            "action": {k: v for k, v in action.items() if not str(k).startswith("_")},
            "act_ms": act_ms,
        }
        if via:
            row["via"] = via
        self._log(row)
        self._log_l0_span_if_direct(action=kind, act_ms=act_ms, via=via)
        out = {"ok": True, "act_ms": act_ms}
        if via:
            out["via"] = via
        return out

    def _act_pixels(
        self,
        action: dict[str, Any],
        x: int,
        y: int,
        *,
        semantic_hint: str = "",
        via: str | None = None,
    ) -> dict[str, Any]:
        decision = self.safety.check_action(
            action,
            package=self.last_package,
            ui_blob=self.last_xml,
            semantic_hint=semantic_hint,
        )
        if not decision.allow:
            row = {"event": "tap_blocked", "xy": [x, y], **decision.to_dict()}
            if via:
                row["via"] = via
            self._log(row)
            out = {"ok": False, **decision.to_dict()}
            if via:
                out["via"] = via
            return out
        t0 = time.perf_counter()
        self.adb.tap(x, y)
        act_ms = int((time.perf_counter() - t0) * 1000)
        row = {"event": "tap", "xy": [x, y], "hint": semantic_hint or None, "act_ms": act_ms}
        if via:
            row["via"] = via
        self._log(row)
        self._log_l0_span_if_direct(action="click", act_ms=act_ms, via=via)
        out: dict[str, Any] = {"ok": True, "act_ms": act_ms}
        if via:
            out["via"] = via
        return out

    def _log(self, row: dict[str, Any]) -> None:
        row = {"ts_ms": _now_ms(), "run_id": self.run_id, **row}
        self._journal.append(row)
        path = self.run_dir / "journal.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def journal_tail(self, n: int = 20) -> list[dict[str, Any]]:
        return self._journal[-n:]

    def log_event(self, row: dict[str, Any]) -> None:
        """Public journal append for higher-level loops (android_run)."""
        self._log(row)
