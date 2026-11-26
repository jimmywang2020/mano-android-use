"""ActClass normalization for Guard (Phase M2).

App-agnostic label heuristics — Host still owns slots; mau only names the act.
``target_key=unknown`` when no world SKU matches (Guard must not fake-idempotent).
"""

from __future__ import annotations

from typing import Any

# Stable act class ids (Host ``policy.banned_act_classes`` uses these strings).
OPEN_SPEC = "open_spec"
CONFIRM_ADD = "confirm_add"
TYPE_QUERY = "type_query"
OPEN_CART = "open_cart"
CHECKOUT = "checkout"
NAVIGATE_BACK = "navigate_back"
SWIPE_SCROLL = "swipe_scroll"
WAIT = "wait"
TERMINATE = "terminate"
TAP_OTHER = "tap_other"

UNKNOWN_TARGET = "unknown"

# Longer / more specific phrases first inside each class.
_CLASS_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        CONFIRM_ADD,
        ("加入购物车", "加购", "选好了", "加入袋中", "Add to cart", "add to bag"),
    ),
    (OPEN_SPEC, ("选规格", "选择规格", "规格", "Customize")),
    (OPEN_CART, ("购物车", "查看购物车", "Cart")),
    (CHECKOUT, ("去结算", "结算", "去下单", "Checkout")),
)


def _norm_blob(*parts: str) -> str:
    return " ".join(str(p or "").strip() for p in parts if str(p or "").strip())


def match_sku_keys(blob: str, sku_keys: list[str] | None) -> str | None:
    """Return the first sku_key that appears as a substring of ``blob`` (or vice versa)."""
    text = (blob or "").strip()
    if not text:
        return None
    for sku in sku_keys or []:
        s = str(sku or "").strip()
        if not s:
            continue
        if s in text or text in s:
            return s
    return None


def resolve_target_key(
    *,
    hint: str = "",
    text: str = "",
    goal: str = "",
    sku_keys: list[str] | None = None,
) -> str:
    """Prefer hint/text match; goal only if exactly one world sku is mentioned."""
    keys = [str(s).strip() for s in (sku_keys or []) if str(s).strip()]
    for source in (hint, text):
        hit = match_sku_keys(source, keys)
        if hit:
            return hit
    goal_hits = [s for s in keys if s in (goal or "")]
    if len(goal_hits) == 1:
        return goal_hits[0]
    return UNKNOWN_TARGET


def classify_act_class(
    *,
    kind: str = "",
    hint: str = "",
    text: str = "",
    button: str = "",
) -> str:
    """Map a device intent + labels to a coarse ActClass."""
    k = str(kind or "").strip().lower()
    if k in {"type"}:
        return TYPE_QUERY
    if k in {"swipe"}:
        return SWIPE_SCROLL
    if k in {"wait"}:
        return WAIT
    if k in {"terminate"}:
        return TERMINATE
    if k in {"system_button", "key", "system_button_press", "press", "keyevent"}:
        btn = str(button or text or "").strip().upper()
        if btn in {"BACK", "HOME"}:
            return NAVIGATE_BACK
        return TAP_OTHER

    blob = _norm_blob(hint, text, button)
    # Prefer longer phrase hits.
    best_class = ""
    best_len = -1
    for act, phrases in _CLASS_PHRASES:
        for phrase in phrases:
            if phrase and phrase in blob and len(phrase) > best_len:
                best_class = act
                best_len = len(phrase)
    if best_class:
        return best_class
    if k in {"click", "tap", ""}:
        return TAP_OTHER
    return TAP_OTHER


def classify_action(
    action: dict[str, Any] | None = None,
    *,
    kind: str = "",
    hint: str = "",
    goal: str = "",
    sku_keys: list[str] | None = None,
) -> tuple[str, str]:
    """Return ``(act_class, target_key)`` for Guard."""
    action = action or {}
    k = kind or str(action.get("action") or action.get("type") or "")
    text = str(action.get("text") or "")
    button = str(action.get("button") or action.get("button_name") or "")
    act = classify_act_class(kind=k, hint=hint, text=text, button=button)
    target = resolve_target_key(
        hint=hint,
        text=text,
        goal=goal,
        sku_keys=sku_keys,
    )
    return act, target
