"""Local android_run step traces: journal spans → trace.json + CLI summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EVENT_STEP = "android_run_step"
EVENT_PROPOSE_STEP = "propose_step"
EVENT_L0_STEP = "l0_step"
SPAN_EVENTS = frozenset({EVENT_STEP, EVENT_PROPOSE_STEP, EVENT_L0_STEP})

_MS_KEYS = ("observe_ms", "grounder_ms", "act_ms", "step_ms")
_TOKEN_KEYS = ("prompt_tokens", "completion_tokens")


def build_step_span(
    *,
    step: int,
    model: str,
    observe_ms: int,
    grounder_ms: int,
    act_ms: int,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    grounder_calls: int = 0,
    action: str = "",
    via: str = "android_run",
    event: str = EVENT_STEP,
    vlm_skipped: bool = False,
    skip_reason: str = "",
    observe_breakdown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one step span for history + journal."""
    observe_ms = max(0, int(observe_ms))
    grounder_ms = max(0, int(grounder_ms))
    act_ms = max(0, int(act_ms))
    ev = event if event in SPAN_EVENTS else EVENT_STEP
    out = {
        "event": ev,
        "step": int(step),
        "model": model or "",
        "observe_ms": observe_ms,
        "grounder_ms": grounder_ms,
        "act_ms": act_ms,
        "step_ms": observe_ms + grounder_ms + act_ms,
        "prompt_tokens": max(0, int(prompt_tokens)),
        "completion_tokens": max(0, int(completion_tokens)),
        "grounder_calls": max(0, int(grounder_calls)),
        "action": action or "",
        "via": via or "android_run",
        "vlm_skipped": bool(vlm_skipped),
    }
    if skip_reason:
        out["skip_reason"] = str(skip_reason)
    if isinstance(observe_breakdown, dict) and observe_breakdown:
        out["observe_screenshot_ms"] = int(observe_breakdown.get("screenshot_ms") or 0)
        out["observe_xml_ms"] = int(observe_breakdown.get("xml_ms") or 0)
        modes = observe_breakdown.get("modes")
        if isinstance(modes, list) and modes:
            out["observe_modes"] = [str(m) for m in modes]
        final_mode = observe_breakdown.get("final_mode") or (
            modes[-1] if isinstance(modes, list) and modes else ""
        )
        if final_mode:
            out["observe_mode"] = str(final_mode)
    return out


def load_step_spans(run_dir: Path | str) -> list[dict[str, Any]]:
    """Load timing spans from journal.jsonl (android_run + propose + L0)."""
    path = Path(run_dir) / "journal.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") not in SPAN_EVENTS:
            continue
        out.append(row)
    return out


def spans_from_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Fallback: collect timing dicts attached to android_run history entries."""
    out: list[dict[str, Any]] = []
    for entry in history or []:
        timing = entry.get("timing")
        if isinstance(timing, dict) and timing.get("event") in SPAN_EVENTS:
            out.append(dict(timing))
        elif isinstance(timing, dict) and any(k in timing for k in _MS_KEYS):
            row = dict(timing)
            row.setdefault("event", EVENT_STEP)
            out.append(row)
    return out


def _via_bucket(row: dict[str, Any]) -> str:
    via = str(row.get("via") or "")
    ev = str(row.get("event") or "")
    if via in {
        "android_run",
        "propose",
        "l0_direct",
        "propose_execute",
        "tree_shortcut",
        "unchanged_recover",
    }:
        return via
    if ev == EVENT_PROPOSE_STEP:
        return "propose"
    if ev == EVENT_L0_STEP:
        return "l0_direct"
    return via or "android_run"


def aggregate_totals(steps: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "steps": len(steps),
        "observe_ms": 0,
        "grounder_ms": 0,
        "act_ms": 0,
        "step_ms": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "grounder_calls": 0,
        "vlm_skipped": 0,
        "observe_screenshot_ms": 0,
        "observe_xml_ms": 0,
        "by_via": {},
        "by_observe_mode": {},
    }
    for row in steps:
        for key in _MS_KEYS:
            totals[key] += int(row.get(key) or 0)
        for key in _TOKEN_KEYS:
            totals[key] += int(row.get(key) or 0)
        totals["grounder_calls"] += int(row.get("grounder_calls") or 0)
        totals["observe_screenshot_ms"] += int(row.get("observe_screenshot_ms") or 0)
        totals["observe_xml_ms"] += int(row.get("observe_xml_ms") or 0)
        if row.get("vlm_skipped"):
            totals["vlm_skipped"] += 1
        modes = row.get("observe_modes")
        if isinstance(modes, list):
            for m in modes:
                key = str(m or "")
                if key:
                    totals["by_observe_mode"][key] = int(totals["by_observe_mode"].get(key) or 0) + 1
        elif row.get("observe_mode"):
            key = str(row.get("observe_mode"))
            totals["by_observe_mode"][key] = int(totals["by_observe_mode"].get(key) or 0) + 1
        bucket = _via_bucket(row)
        slot = totals["by_via"].setdefault(
            bucket,
            {"steps": 0, "step_ms": 0, "prompt_tokens": 0, "completion_tokens": 0},
        )
        slot["steps"] += 1
        slot["step_ms"] += int(row.get("step_ms") or 0)
        slot["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
        slot["completion_tokens"] += int(row.get("completion_tokens") or 0)
    return totals


def build_trace_doc(
    *,
    run_id: str,
    goal: str,
    status: str,
    model: str,
    steps: list[dict[str, Any]],
    run_dir: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "goal": goal,
        "status": status,
        "model": model,
        "run_dir": run_dir or "",
        "totals": aggregate_totals(steps),
        "steps": steps,
    }


def write_trace(
    run_dir: Path | str,
    *,
    run_id: str,
    goal: str,
    status: str,
    model: str,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rebuild trace.json from journal (preferred) or history timings."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    steps = load_step_spans(run_dir)
    if not steps:
        steps = spans_from_history(history)
    doc = build_trace_doc(
        run_id=run_id,
        goal=goal,
        status=status,
        model=model,
        steps=steps,
        run_dir=str(run_dir),
    )
    path = run_dir / "trace.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def resolve_trace_target(target: str | None, *, runs_root: str | Path = "runs") -> Path:
    """Resolve CLI path: empty → newest runs/*; dir; or trace.json / journal parent."""
    if target:
        path = Path(target).expanduser()
        if path.is_file():
            return path.parent if path.name in {"trace.json", "journal.jsonl"} else path
        if path.is_dir():
            return path
        raise FileNotFoundError(f"trace target not found: {target}")

    root = Path(runs_root)
    if not root.is_dir():
        raise FileNotFoundError(f"runs root not found: {root}")
    candidates = [p for p in root.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no run dirs under {root}")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def load_trace(run_dir: Path | str) -> dict[str, Any]:
    """Load trace.json if present; else rebuild from journal only."""
    run_dir = Path(run_dir)
    path = run_dir / "trace.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    steps = load_step_spans(run_dir)
    return build_trace_doc(
        run_id=run_dir.name,
        goal="",
        status="",
        model="",
        steps=steps,
        run_dir=str(run_dir),
    )


def format_trace_table(doc: dict[str, Any]) -> str:
    steps = list(doc.get("steps") or [])
    totals = doc.get("totals") or aggregate_totals(steps)
    lines = [
        f"run_id={doc.get('run_id') or ''}  status={doc.get('status') or ''}  model={doc.get('model') or ''}",
        f"goal={doc.get('goal') or ''}",
        "",
        f"{'step':>4}  {'obs_ms':>8}  {'vlm_ms':>8}  {'act_ms':>8}  {'step_ms':>8}  "
        f"{'ptok':>6}  {'ctok':>6}  {'via':<16}  action",
        "-" * 96,
    ]
    for row in steps:
        lines.append(
            f"{int(row.get('step') or 0):>4}  "
            f"{int(row.get('observe_ms') or 0):>8}  "
            f"{int(row.get('grounder_ms') or 0):>8}  "
            f"{int(row.get('act_ms') or 0):>8}  "
            f"{int(row.get('step_ms') or 0):>8}  "
            f"{int(row.get('prompt_tokens') or 0):>6}  "
            f"{int(row.get('completion_tokens') or 0):>6}  "
            f"{str(row.get('via') or ''):<16}  "
            f"{row.get('action') or ''}"
        )
    lines.append("-" * 96)
    lines.append(
        f"{'tot':>4}  "
        f"{int(totals.get('observe_ms') or 0):>8}  "
        f"{int(totals.get('grounder_ms') or 0):>8}  "
        f"{int(totals.get('act_ms') or 0):>8}  "
        f"{int(totals.get('step_ms') or 0):>8}  "
        f"{int(totals.get('prompt_tokens') or 0):>6}  "
        f"{int(totals.get('completion_tokens') or 0):>6}  "
        f"{'':16}  "
        f"steps={int(totals.get('steps') or 0)}"
    )
    by_via = totals.get("by_via") or {}
    if by_via:
        bits = [
            f"{k}:{int(v.get('steps') or 0)}/{_fmt_ms(int(v.get('step_ms') or 0))}"
            for k, v in sorted(by_via.items())
            if isinstance(v, dict)
        ]
        lines.append("by_via  " + "  ".join(bits))
    return "\n".join(lines)


def trace_summary_from_doc(doc: dict[str, Any]) -> dict[str, Any]:
    totals = doc.get("totals") or aggregate_totals(list(doc.get("steps") or []))
    return {
        "step_ms_total": int(totals.get("step_ms") or 0),
        "observe_ms_total": int(totals.get("observe_ms") or 0),
        "grounder_ms_total": int(totals.get("grounder_ms") or 0),
        "act_ms_total": int(totals.get("act_ms") or 0),
        "prompt_tokens": int(totals.get("prompt_tokens") or 0),
        "completion_tokens": int(totals.get("completion_tokens") or 0),
        "steps": int(totals.get("steps") or 0),
    }


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(100.0 * part / whole, 1)


def _fmt_ms(ms: int) -> str:
    ms = max(0, int(ms))
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def cost_report_from_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Host-facing breakdown: who spent time/tokens (observe / VLM / act)."""
    steps = list(doc.get("steps") or [])
    totals = doc.get("totals") if isinstance(doc.get("totals"), dict) else None
    if totals is None:
        totals = aggregate_totals(steps)
    obs = int(totals.get("observe_ms") or 0)
    vlm = int(totals.get("grounder_ms") or 0)
    act = int(totals.get("act_ms") or 0)
    total = int(totals.get("step_ms") or (obs + vlm + act))
    ptok = int(totals.get("prompt_tokens") or 0)
    ctok = int(totals.get("completion_tokens") or 0)
    n = int(totals.get("steps") or len(steps))
    by_via = totals.get("by_via") if isinstance(totals.get("by_via"), dict) else {}
    if not by_via:
        by_via = aggregate_totals(steps).get("by_via") or {}

    shot_ms = int(totals.get("observe_screenshot_ms") or 0)
    xml_ms = int(totals.get("observe_xml_ms") or 0)
    by_mode = totals.get("by_observe_mode") if isinstance(totals.get("by_observe_mode"), dict) else {}
    by_phase = {
        "observe": {
            "ms": obs,
            "pct": _pct(obs, total),
            "what": "ADB capture (android_run: full every step; L0 may use tree/shot)",
            "screenshot_ms": shot_ms,
            "xml_ms": xml_ms,
            "by_mode": dict(by_mode) if by_mode else {},
        },
        "grounder": {
            "ms": vlm,
            "pct": _pct(vlm, total),
            "what": "VLM propose (main token consumer)",
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        },
        "act": {
            "ms": act,
            "pct": _pct(act, total),
            "what": "tap / swipe / type / press via L0",
        },
    }
    vlm_skipped = int(totals.get("vlm_skipped") or 0)
    if not vlm_skipped:
        vlm_skipped = sum(1 for row in steps if row.get("vlm_skipped"))
    step_rows = [
        {
            "step": int(row.get("step") or 0),
            "action": str(row.get("action") or ""),
            "via": str(row.get("via") or ""),
            "vlm_skipped": bool(row.get("vlm_skipped")),
            "skip_reason": str(row.get("skip_reason") or ""),
            "observe_ms": int(row.get("observe_ms") or 0),
            "grounder_ms": int(row.get("grounder_ms") or 0),
            "act_ms": int(row.get("act_ms") or 0),
            "step_ms": int(row.get("step_ms") or 0),
            "prompt_tokens": int(row.get("prompt_tokens") or 0),
            "completion_tokens": int(row.get("completion_tokens") or 0),
        }
        for row in steps
    ]
    dominant = max(
        (("observe", obs), ("grounder", vlm), ("act", act)),
        key=lambda x: x[1],
    )[0]
    bypass_ms = sum(
        int((by_via.get(k) or {}).get("step_ms") or 0)
        for k in ("propose", "l0_direct", "propose_execute", "tree_shortcut", "unchanged_recover")
    )
    narrative = (
        f"Total {_fmt_ms(total)} across {n} step(s). "
        f"Breakdown: observe {_fmt_ms(obs)} ({by_phase['observe']['pct']}%), "
        f"grounder/VLM {_fmt_ms(vlm)} ({by_phase['grounder']['pct']}%), "
        f"act {_fmt_ms(act)} ({by_phase['act']['pct']}%). "
        f"Tokens: {ptok} prompt + {ctok} completion (grounder only). "
        f"Dominant: {dominant}."
    )
    if vlm_skipped:
        narrative += f" VLM skipped on {vlm_skipped} step(s)."
    if bypass_ms > 0:
        narrative += f" Includes bypass via propose/L0/tree/recover: {_fmt_ms(bypass_ms)}."
    if shot_ms or xml_ms or by_mode:
        mode_bits = ",".join(f"{k}×{v}" for k, v in sorted(by_mode.items())) if by_mode else ""
        narrative += (
            f" Observe split: screenshot {_fmt_ms(shot_ms)}, xml {_fmt_ms(xml_ms)}"
            + (f" (modes {mode_bits})." if mode_bits else ".")
        )
    return {
        "total_ms": total,
        "steps": n,
        "prompt_tokens": ptok,
        "completion_tokens": ctok,
        "grounder_calls": int(totals.get("grounder_calls") or 0),
        "vlm_skipped": vlm_skipped,
        "by_phase": by_phase,
        "by_via": by_via,
        "dominant_phase": dominant,
        "per_step": step_rows,
        "narrative": narrative,
    }


def cost_report_from_history(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    steps = spans_from_history(history)
    return cost_report_from_doc({"steps": steps, "totals": aggregate_totals(steps)})


def plan_cost_report(stage_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-stage cost_report from PlanResult.stages rows."""
    stages_out: list[dict[str, Any]] = []
    total_ms = 0
    ptok = 0
    ctok = 0
    obs = vlm = act = 0
    for row in stage_rows:
        sid = str(row.get("id") or "")
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        cr = result.get("cost_report") if isinstance(result, dict) else None
        if not isinstance(cr, dict):
            hist = result.get("history") if isinstance(result, dict) else None
            cr = cost_report_from_history(hist if isinstance(hist, list) else [])
        stages_out.append(
            {
                "id": sid,
                "status": result.get("status") if isinstance(result, dict) else "",
                "goal": row.get("goal") or (result.get("goal") if isinstance(result, dict) else ""),
                "total_ms": int(cr.get("total_ms") or 0),
                "prompt_tokens": int(cr.get("prompt_tokens") or 0),
                "completion_tokens": int(cr.get("completion_tokens") or 0),
                "dominant_phase": cr.get("dominant_phase") or "",
                "by_phase": cr.get("by_phase") or {},
                "narrative": cr.get("narrative") or "",
            }
        )
        total_ms += int(cr.get("total_ms") or 0)
        ptok += int(cr.get("prompt_tokens") or 0)
        ctok += int(cr.get("completion_tokens") or 0)
        bp = cr.get("by_phase") or {}
        obs += int((bp.get("observe") or {}).get("ms") or 0)
        vlm += int((bp.get("grounder") or {}).get("ms") or 0)
        act += int((bp.get("act") or {}).get("ms") or 0)

    by_phase = {
        "observe": {"ms": obs, "pct": _pct(obs, total_ms), "what": "ADB screenshot + accessibility tree"},
        "grounder": {
            "ms": vlm,
            "pct": _pct(vlm, total_ms),
            "what": "VLM propose (main token consumer)",
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
        },
        "act": {"ms": act, "pct": _pct(act, total_ms), "what": "tap / swipe / type / press via L0"},
    }
    dominant = max(
        (("observe", obs), ("grounder", vlm), ("act", act)),
        key=lambda x: x[1],
    )[0]
    stage_bits = ", ".join(
        f"{s['id']} {_fmt_ms(int(s['total_ms']))}" for s in stages_out
    ) or "(none)"
    narrative = (
        f"Plan total {_fmt_ms(total_ms)} over {len(stages_out)} stage(s) [{stage_bits}]. "
        f"Phases: observe {_fmt_ms(obs)} ({by_phase['observe']['pct']}%), "
        f"grounder/VLM {_fmt_ms(vlm)} ({by_phase['grounder']['pct']}%), "
        f"act {_fmt_ms(act)} ({by_phase['act']['pct']}%). "
        f"Tokens: {ptok} prompt + {ctok} completion. Dominant: {dominant}."
    )
    return {
        "total_ms": total_ms,
        "prompt_tokens": ptok,
        "completion_tokens": ctok,
        "by_phase": by_phase,
        "dominant_phase": dominant,
        "stages": stages_out,
        "narrative": narrative,
    }
