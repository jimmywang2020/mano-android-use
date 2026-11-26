"""Phase O4: rebuild a *draft* TaskState / ResumeSpec from a run journal.

Used when Cursor MCP returns ``-32001`` / empty and Host never saw ``task_patch``.

Hard rules:
- ``cart_count`` only from a11y「已添加N件」patterns (``world_evidence``), never from
  counting ``GOAL_REACHED`` / ``android_run_stop`` events.
- ``completed_slots`` is left empty unless a slots file is passed and cart_count
  maps to a **suggested** prefix (marked ``needs_confirm``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_loop import continue_hint_for_run
from .trace_report import resolve_trace_target
from .world_evidence import extract_cart_count, suggest_world_progress


def _read_journal(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "journal.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _blob_from_row(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("summary", "last_summary", "screen_summary", "reason"):
        val = row.get(key)
        if val:
            parts.append(str(val))
    labels = row.get("labels")
    if isinstance(labels, list):
        parts.extend(str(x) for x in labels if str(x).strip())
    obs = row.get("observe") or row.get("screen")
    if isinstance(obs, dict):
        parts.append(str(obs.get("summary") or ""))
        labs = obs.get("labels")
        if isinstance(labs, list):
            parts.extend(str(x) for x in labs if str(x).strip())
    return "\n".join(p for p in parts if p.strip())


def _suggest_slots_from_cart(
    cart_count: int | None,
    slots_path: Path | str | None,
) -> tuple[list[str], list[str]]:
    """Return (suggested completed_slots, notes). Conservative dual-drink-style map."""
    notes: list[str] = []
    if cart_count is None or not slots_path:
        return [], notes
    path = Path(slots_path)
    if not path.is_file():
        notes.append(f"slots_path not found: {path}")
        return [], notes
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        notes.append(f"slots_path unreadable: {exc}")
        return [], notes
    slots = data.get("slots") or data.get("stages") or []
    ids = [str(s.get("id") or "").strip() for s in slots if isinstance(s, dict)]
    ids = [i for i in ids if i]
    if not ids:
        return [], notes
    # Heuristic: first slot = enter; optional menu bridges (A2_open_menu); then one
    # acquire per cart item; never mark verify. Bridges are completed whenever
    # cart_count>=1 (menu must already be open to have added).
    def _is_verify(sid: str) -> bool:
        low = sid.lower()
        return low.startswith(("d_", "verify", "check"))

    def _is_bridge(sid: str) -> bool:
        low = sid.lower()
        return "open_menu" in low or low.startswith("a2_")

    non_verify = [i for i in ids if not _is_verify(i)]
    if len(non_verify) >= 2 and ids and non_verify[0] == ids[0]:
        enter, rest = non_verify[0], non_verify[1:]
        bridges = [i for i in rest if _is_bridge(i)]
        buys = [i for i in rest if not _is_bridge(i)]
        n = max(0, int(cart_count))
        suggested = [enter]
        if n >= 1:
            suggested.extend(bridges)
        suggested.extend(buys[:n])
        notes.append(
            f"Heuristic from cart_count={cart_count}: suggested completed_slots={suggested} "
            "(verify Host with find; do not trust GOAL event counts)."
        )
        return suggested, notes
    notes.append("Could not map cart_count to slots; leave completed_slots empty.")
    return [], notes


def resume_from_run(
    target: str | Path | None = None,
    *,
    runs_root: str | Path = "runs",
    slots_path: str | Path | None = None,
    goal: str = "",
) -> dict[str, Any]:
    """Build a draft resume blob from ``runs/<id>/journal.jsonl``.

    Does not talk to the device. Host must confirm ``needs_confirm`` fields before
    treating draft_progress as TaskState truth.
    """
    warnings: list[str] = []
    needs_confirm: list[str] = ["completed_slots", "sku_keys", "policy"]
    try:
        run_dir = resolve_trace_target(target, runs_root=runs_root)
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "code": "RUN_NOT_FOUND",
            "reason": str(exc),
            "warnings": [str(exc)],
            "needs_confirm": needs_confirm,
        }

    rows = _read_journal(run_dir)
    if not rows:
        return {
            "ok": False,
            "code": "EMPTY_JOURNAL",
            "reason": f"no journal events in {run_dir}",
            "run_dir": str(run_dir),
            "warnings": ["empty journal"],
            "needs_confirm": needs_confirm,
        }

    stops = [r for r in rows if r.get("event") == "android_run_stop"]
    last_stop = stops[-1] if stops else {}
    last_status = str(last_stop.get("status") or "")
    goal_events = sum(
        1 for r in stops if str(r.get("status") or "") == "GOAL_REACHED"
    )
    if goal_events:
        warnings.append(
            f"Saw {goal_events}× android_run_stop GOAL_REACHED — "
            "do NOT use that count as cart_count or dual-drink PASS."
        )

    # Prefer newest row with a usable summary blob for cart_count.
    summary = ""
    package = ""
    for row in reversed(rows):
        blob = _blob_from_row(row)
        # Skip stop-reason crumbs like "wall_budget_ms" with no UI text.
        if blob and not summary and ("labels=" in blob or "已添加" in blob or "package=" in blob):
            summary = blob
        elif blob and not summary and len(blob) > 40:
            summary = blob
        pkg = row.get("package") or (row.get("screen") or {}).get("package")
        if pkg and not package:
            package = str(pkg)
        if summary and package:
            break
    if not summary and last_stop:
        summary = _blob_from_row(last_stop)

    # Also scan newest step-*.xml under run_dir (compact journal often omits cart badge).
    xml_blob = ""
    xmls = sorted(run_dir.glob("step-*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    for xp in xmls[:3]:
        try:
            text = xp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if extract_cart_count(text) is not None:
            xml_blob = text
            break
        if not xml_blob and text:
            xml_blob = text[:50_000]

    cart_count = extract_cart_count(summary, xml_blob)
    world_frag = suggest_world_progress(summary=summary, xml=xml_blob)
    draft: dict[str, Any] = dict(world_frag) if world_frag else {}
    if cart_count is None:
        warnings.append(
            "cart_count unknown — no「已添加N件」in journal summaries; "
            "Host must find/observe before advancing dual-drink slots."
        )
        needs_confirm.append("world.cart_count")
    else:
        warnings.append(f"cart_count={cart_count} from a11y text only.")

    suggested_slots, slot_notes = _suggest_slots_from_cart(cart_count, slots_path)
    warnings.extend(slot_notes)
    if suggested_slots:
        draft["completed_slots"] = suggested_slots
        needs_confirm.append("completed_slots_heuristic")
    else:
        draft.setdefault("completed_slots", [])

    resume_goal = (goal or "").strip()
    hint = continue_hint_for_run(
        goal=resume_goal or "(set next slot goal — journal has no goal field)",
        package=package,
        last_summary=summary[:300],
        status=last_status or "TIME_BUDGET",
        progress=draft,
        tree_hints=[],
        success_check=None,
    )
    # Force Host-facing resume shape for lost-MCP.
    hint = {
        **hint,
        "next_actor": "host",
        "suggestion": (
            "Lost MCP / rebuild path: confirm draft_progress (especially cart_count "
            "and completed_slots), then short android_run with omit_package + "
            "progress_json; do not cold-start or re-open full android_run_plan."
        ),
    }

    progress_json = json.dumps(draft, ensure_ascii=False)
    return {
        "ok": True,
        "schema": "mau.resume_from_run.v1",
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "last_status": last_status,
        "last_summary": summary[:500],
        "package": package,
        "goal_reached_stop_count": goal_events,
        "draft_progress": draft,
        "resume": hint,
        "progress_json": progress_json,
        "mcp_hint": {
            "tool": "android_run",
            "omit_package": True,
            "cold_start": False,
            "progress_json": progress_json,
            "note": "Fill goal/tree_hints/success_check for the *next* slot only.",
        },
        "warnings": warnings,
        "needs_confirm": sorted(set(needs_confirm)),
        "dont": list(hint.get("dont") or []),
    }
