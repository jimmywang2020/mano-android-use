"""Anti-redo KPIs from android_run history / trace (Phase M5).

These are observational — Host uses them to gate acceptance, not to drive UI.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .act_class import CONFIRM_ADD, OPEN_SPEC, classify_action
from .trace_report import EVENT_L0_STEP, EVENT_PROPOSE_STEP, EVENT_STEP, SPAN_EVENTS

_REDO_ACT_CLASSES = frozenset({OPEN_SPEC, CONFIRM_ADD})


def _entry_skip_reason(entry: dict[str, Any]) -> str:
    if entry.get("skip_reason"):
        return str(entry.get("skip_reason") or "")
    timing = entry.get("timing") if isinstance(entry.get("timing"), dict) else {}
    return str(timing.get("skip_reason") or "")


def _entry_via(entry: dict[str, Any]) -> str:
    timing = entry.get("timing") if isinstance(entry.get("timing"), dict) else {}
    if timing.get("via"):
        return str(timing.get("via") or "")
    if entry.get("via"):
        return str(entry.get("via") or "")
    return ""


def _entry_guard(entry: dict[str, Any]) -> dict[str, Any]:
    g = entry.get("guard")
    return dict(g) if isinstance(g, dict) else {}


def _executed_device_act(entry: dict[str, Any]) -> bool:
    """True when a real tap/type/swipe hit the device (not guard soft-skip)."""
    sr = _entry_skip_reason(entry)
    if sr in {"guard_noop", "guard_deny", "success_check", "progress_hold", "unchanged_stuck"}:
        return False
    exec_r = entry.get("execution") if isinstance(entry.get("execution"), dict) else {}
    if exec_r.get("guard") and not exec_r.get("ok"):
        return False
    if exec_r.get("guard") and exec_r.get("code") in {"GUARD_NOOP", "GUARD_DENY"}:
        return False
    via = _entry_via(entry)
    if via in {"tree_shortcut", "android_run"} and exec_r.get("ok"):
        kind = str((entry.get("action") or entry.get("mapped") or {}).get("action") or "")
        if not kind:
            # tree_shortcut path stores action on timing
            timing = entry.get("timing") if isinstance(entry.get("timing"), dict) else {}
            kind = str(timing.get("action") or "")
        if kind in {"wait", "terminate", ""}:
            # empty action with tree_shortcut still means click
            if via == "tree_shortcut":
                return True
            return False
        if kind == "terminate":
            return False
        return True
    return False


def _act_key(entry: dict[str, Any]) -> tuple[str, str]:
    guard = _entry_guard(entry)
    act = str(guard.get("act_class") or "")
    target = str(guard.get("target_key") or "unknown")
    if act:
        return act, target
    action = entry.get("action") if isinstance(entry.get("action"), dict) else {}
    mapped = entry.get("mapped") if isinstance(entry.get("mapped"), dict) else {}
    kind = str(action.get("action") or mapped.get("action") or "")
    hint = ""
    ts = entry.get("tree_shortcut") if isinstance(entry.get("tree_shortcut"), dict) else {}
    if ts.get("query"):
        hint = str(ts.get("query") or "")
    act, target = classify_action(action or {"action": kind or "click"}, hint=hint, goal="")
    return act, target


def kpis_from_history(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Compute M5 KPIs for one ``android_run`` history list."""
    rows = list(history or [])
    guard_noop = 0
    guard_deny = 0
    acquire_after_cart = 0
    cart_seen = False
    executed_counts: Counter[tuple[str, str]] = Counter()
    redo_same_act_class = 0

    tree_shortcut_miss = 0
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        sr = _entry_skip_reason(entry)
        if sr == "guard_noop":
            guard_noop += 1
        elif sr == "guard_deny":
            guard_deny += 1
        if entry.get("tree_shortcut_miss") or sr == "tree_shortcut_miss":
            tree_shortcut_miss += 1

        if not _executed_device_act(entry):
            prog = entry.get("progress") if isinstance(entry.get("progress"), dict) else {}
            if prog.get("cart_seen") or (
                isinstance(prog.get("world"), dict) and prog["world"].get("cart_count")
            ):
                cart_seen = True
            continue
        act, target = _act_key(entry)
        key = (act, target)
        if act in _REDO_ACT_CLASSES and executed_counts[key] >= 1:
            redo_same_act_class += 1
        if cart_seen and act in _REDO_ACT_CLASSES:
            # Device acquire after cart evidence — likely verify-via-add loop
            acquire_after_cart += 1
        executed_counts[key] += 1
        prog = entry.get("progress") if isinstance(entry.get("progress"), dict) else {}
        if prog.get("cart_seen") or (
            isinstance(prog.get("world"), dict) and prog["world"].get("cart_count")
        ):
            cart_seen = True

    return {
        "android_run_rounds": 1 if rows else 0,
        "steps": len(rows),
        "guard_noop": guard_noop,
        "guard_deny": guard_deny,
        "tree_shortcut_miss": tree_shortcut_miss,
        "redo_same_act_class": redo_same_act_class,
        "acquire_after_cart": acquire_after_cart,
        "executed_by_act_class": {
            f"{a}|{t}": n for (a, t), n in sorted(executed_counts.items())
        },
    }


def kpis_from_spans(spans: list[dict[str, Any]] | None) -> dict[str, Any]:
    """KPI subset from journal timing spans (trace.json / mau kpi)."""
    rows = [r for r in (spans or []) if isinstance(r, dict)]
    by_event: Counter[str] = Counter()
    by_via: Counter[str] = Counter()
    guard_noop = 0
    guard_deny = 0
    tree_shortcut_miss = 0
    redo = 0
    executed_counts: Counter[tuple[str, str]] = Counter()

    for row in rows:
        ev = str(row.get("event") or EVENT_STEP)
        if ev in SPAN_EVENTS:
            by_event[ev] += 1
        if ev == "tree_shortcut_miss" or row.get("tree_shortcut_miss"):
            tree_shortcut_miss += 1
        via = str(row.get("via") or "")
        if via:
            by_via[via] += 1
        sr = str(row.get("skip_reason") or "")
        if sr == "guard_noop":
            guard_noop += 1
        elif sr == "guard_deny":
            guard_deny += 1
        elif sr == "tree_shortcut_miss" and ev != "tree_shortcut_miss":
            tree_shortcut_miss += 1
        act = str(row.get("act_class") or "")
        target = str(row.get("target_key") or "unknown")
        if (
            act in _REDO_ACT_CLASSES
            and sr not in {"guard_noop", "guard_deny"}
            and via in {"tree_shortcut", "android_run"}
            and int(row.get("act_ms") or 0) > 0
        ):
            key = (act, target)
            if executed_counts[key] >= 1:
                redo += 1
            executed_counts[key] += 1

    run_steps = int(by_event.get(EVENT_STEP) or 0)
    l0_steps = int(by_event.get(EVENT_L0_STEP) or 0)
    propose_steps = int(by_event.get(EVENT_PROPOSE_STEP) or 0)
    host_loop_denom = run_steps + l0_steps + propose_steps
    l0_share = round(100.0 * l0_steps / host_loop_denom, 1) if host_loop_denom else 0.0
    # Count android_run rounds ≈ distinct run stops not available on spans alone;
    # use presence of android_run_step as one round when only one run_dir.
    return {
        "android_run_rounds": 1 if run_steps else 0,
        "android_run_steps": run_steps,
        "l0_steps": l0_steps,
        "propose_steps": propose_steps,
        "l0_as_main_loop_share_pct": l0_share,
        "guard_noop": guard_noop,
        "guard_deny": guard_deny,
        "tree_shortcut_miss": tree_shortcut_miss,
        "redo_same_act_class": redo,
        "by_via": dict(by_via),
    }


def merge_kpi_views(
    history_kpis: dict[str, Any] | None = None,
    span_kpis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prefer history-derived redo/guard; fill loop-share from spans."""
    out: dict[str, Any] = {}
    if span_kpis:
        out.update(span_kpis)
    if history_kpis:
        for k in (
            "guard_noop",
            "guard_deny",
            "tree_shortcut_miss",
            "redo_same_act_class",
            "acquire_after_cart",
            "executed_by_act_class",
            "steps",
            "android_run_rounds",
        ):
            if k in history_kpis:
                out[k] = history_kpis[k]
    return out


def kpi_narrative(kpis: dict[str, Any] | None) -> str:
    if not kpis:
        return ""
    bits = []
    if "redo_same_act_class" in kpis:
        bits.append(f"redo_same_act_class={kpis.get('redo_same_act_class')}")
    if "guard_noop" in kpis or "guard_deny" in kpis:
        bits.append(
            f"guard_noop={kpis.get('guard_noop', 0)} deny={kpis.get('guard_deny', 0)}"
        )
    if kpis.get("tree_shortcut_miss"):
        bits.append(f"tree_shortcut_miss={kpis.get('tree_shortcut_miss')}")
    if "acquire_after_cart" in kpis:
        bits.append(f"acquire_after_cart={kpis.get('acquire_after_cart')}")
    if "l0_as_main_loop_share_pct" in kpis:
        bits.append(f"l0_share={kpis.get('l0_as_main_loop_share_pct')}%")
    if "android_run_rounds" in kpis:
        bits.append(f"android_run_rounds={kpis.get('android_run_rounds')}")
    if not bits:
        return ""
    return "KPIs: " + ", ".join(bits) + "."


def format_kpi_table(kpis: dict[str, Any] | None) -> str:
    if not kpis:
        return "(no kpis)"
    lines = ["kpi                              value"]
    for key in (
        "android_run_rounds",
        "android_run_steps",
        "l0_steps",
        "propose_steps",
        "l0_as_main_loop_share_pct",
        "guard_noop",
        "guard_deny",
        "tree_shortcut_miss",
        "redo_same_act_class",
        "acquire_after_cart",
        "steps",
    ):
        if key in kpis:
            lines.append(f"{key:<32} {kpis[key]}")
    return "\n".join(lines)
