"""Host TaskState progress contract (Phase M1).

``progress`` stays a plain dict for MCP/CLI JSON, but merges understand:

- ``completed_slots``: ordered unique list of slot ids (union)
- ``world``: observational facts Host/mau share — ``cart_count`` (max int),
  ``sku_keys`` (union list); other keys forward-compatible
- ``policy``: Host-authored bans for later Guard (M2) —
  ``banned_act_classes`` / ``banned_hint_labels`` (union lists)

Legacy flat bits (``fare_seen``, ``cart_seen``, ``saw:…``, ``goal_matched``) keep
truthy OR-merge. mau does **not** auto-infer SKUs from UI here.
"""

from __future__ import annotations

from typing import Any

COMPLETED_SLOTS_KEY = "completed_slots"
WORLD_KEY = "world"
POLICY_KEY = "policy"

WORLD_LIST_KEYS = frozenset({"sku_keys"})
WORLD_MAX_INT_KEYS = frozenset({"cart_count"})
POLICY_LIST_KEYS = frozenset({"banned_act_classes", "banned_hint_labels"})
CONTRACT_KEYS = frozenset({COMPLETED_SLOTS_KEY, WORLD_KEY, POLICY_KEY})


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            s = str(item).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out
    return []


def _union_str_list(base: Any, extra: Any) -> list[str]:
    return _as_str_list(list(_as_str_list(base)) + list(_as_str_list(extra)))


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_progress(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce contract fields; leave unknown keys intact (forward-compatible)."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key)
        if k == COMPLETED_SLOTS_KEY:
            out[k] = _as_str_list(value)
        elif k == WORLD_KEY and isinstance(value, dict):
            world: dict[str, Any] = {}
            for wk, wv in value.items():
                wsk = str(wk)
                if wsk in WORLD_LIST_KEYS:
                    world[wsk] = _as_str_list(wv)
                elif wsk in WORLD_MAX_INT_KEYS:
                    iv = _as_int(wv)
                    if iv is not None:
                        world[wsk] = iv
                else:
                    world[wsk] = wv
            out[k] = world
        elif k == POLICY_KEY and isinstance(value, dict):
            policy: dict[str, Any] = {}
            for pk, pv in value.items():
                psk = str(pk)
                if psk in POLICY_LIST_KEYS:
                    policy[psk] = _as_str_list(pv)
                else:
                    policy[psk] = pv
            out[k] = policy
        else:
            out[k] = value
    return out


def or_merge_progress(
    base: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """OR-merge progress for Host TaskState / plan stages / android_run seeds.

    - ``completed_slots`` / list policy+sku fields: ordered union
    - ``world.cart_count``: max int (0 is kept)
    - nested ``world`` / ``policy``: deep-merge, not replace
    - legacy scalar bits: truthy overwrite only (False never clears True)
    """
    out = normalize_progress(base)
    for key, value in normalize_progress(extra).items():
        if key == COMPLETED_SLOTS_KEY:
            out[key] = _union_str_list(out.get(key), value)
            continue
        if key == WORLD_KEY and isinstance(value, dict):
            world = dict(out[WORLD_KEY]) if isinstance(out.get(WORLD_KEY), dict) else {}
            for wk, wv in value.items():
                if wk in WORLD_LIST_KEYS:
                    world[wk] = _union_str_list(world.get(wk), wv)
                elif wk in WORLD_MAX_INT_KEYS:
                    iv = _as_int(wv)
                    if iv is None:
                        continue
                    prev = _as_int(world.get(wk))
                    world[wk] = iv if prev is None else max(prev, iv)
                elif wv or wv == 0 or wv is False:
                    world[wk] = wv
            out[WORLD_KEY] = world
            continue
        if key == POLICY_KEY and isinstance(value, dict):
            policy = dict(out[POLICY_KEY]) if isinstance(out.get(POLICY_KEY), dict) else {}
            for pk, pv in value.items():
                if pk in POLICY_LIST_KEYS:
                    policy[pk] = _union_str_list(policy.get(pk), pv)
                elif pv or pv == 0 or pv is False:
                    policy[pk] = pv
            out[POLICY_KEY] = policy
            continue
        if value:
            out[key] = value
    return out


def cart_or_fare_hold(progress: dict[str, Any] | None) -> bool:
    """Whether unchanged-screen recover should hold (no suicide BACK)."""
    prog = normalize_progress(progress)
    if prog.get("fare_seen") or prog.get("cart_seen"):
        return True
    world = prog.get(WORLD_KEY)
    if isinstance(world, dict):
        count = _as_int(world.get("cart_count"))
        if count is not None and count > 0:
            return True
        if _as_str_list(world.get("sku_keys")):
            return True
    return False


def progress_prompt_lines(progress: dict[str, Any] | None) -> list[str]:
    """Token-light lines for Grounder / PlanState (do-not-redo)."""
    prog = normalize_progress(progress)
    if not prog:
        return []
    lines: list[str] = []
    slots = _as_str_list(prog.get(COMPLETED_SLOTS_KEY))
    if slots:
        lines.append("Completed slots (do not redo): " + ", ".join(slots[:16]) + ".")
    world = prog.get(WORLD_KEY) if isinstance(prog.get(WORLD_KEY), dict) else {}
    world_bits: list[str] = []
    if isinstance(world, dict) and world:
        if "cart_count" in world:
            world_bits.append(f"cart_count={world['cart_count']}")
        skus = _as_str_list(world.get("sku_keys"))
        if skus:
            world_bits.append("sku_keys=[" + ", ".join(skus[:8]) + "]")
        for wk, wv in world.items():
            if wk in WORLD_LIST_KEYS or wk in WORLD_MAX_INT_KEYS:
                continue
            if wv or wv == 0:
                world_bits.append(f"{wk}={wv}")
        if world_bits:
            lines.append("World state: " + "; ".join(world_bits[:12]) + ".")
    policy = prog.get(POLICY_KEY) if isinstance(prog.get(POLICY_KEY), dict) else {}
    if isinstance(policy, dict) and policy:
        banned_acts = _as_str_list(policy.get("banned_act_classes"))
        banned_hints = _as_str_list(policy.get("banned_hint_labels"))
        if banned_acts:
            lines.append(
                "Banned act classes (do not perform): " + ", ".join(banned_acts[:12]) + "."
            )
        if banned_hints:
            lines.append(
                "Banned hint labels (do not tree-shortcut): "
                + ", ".join(banned_hints[:12])
                + "."
            )
    legacy = [
        str(k)
        for k, v in prog.items()
        if v and str(k) not in CONTRACT_KEYS
    ][:12]
    if legacy:
        lines.append("Known progress bits (do not undo): " + ", ".join(legacy) + ".")
    if cart_or_fare_hold(prog):
        lines.append(
            "Progress hold: fare/cart already seen — do not press BACK/HOME; "
            "prefer terminate:success if the quote/cart UI is visible."
        )
    return lines
