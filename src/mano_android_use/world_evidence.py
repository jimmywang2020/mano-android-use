"""Lightweight world-state evidence from observe blobs (Phase M4).

Suggests ``progress.world`` patches Host can OR-merge — mau does **not** invent
``sku_keys`` from screenshots. Cart count comes from stable a11y strings like
「购物车，已添加1件商品」.
"""

from __future__ import annotations

import re
from typing import Any

# Prefer specific Meituan/cart phrasings; first match wins (left to right).
_CART_COUNT_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"已添加\s*(\d+)\s*件"),
    re.compile(r"购物车[，,\s]*已添加\s*(\d+)"),
    re.compile(r"cart[^\d]{0,12}(\d+)\s*item", re.IGNORECASE),
)


def extract_cart_count(*blobs: str) -> int | None:
    """Return cart item count if a known pattern appears, else None."""
    text = "\n".join(str(b or "") for b in blobs)
    if not text.strip():
        return None
    for pat in _CART_COUNT_RES:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    return None


def suggest_world_progress(
    *,
    summary: str = "",
    xml: str = "",
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Build a progress fragment with optional ``world.cart_count`` (may be empty)."""
    label_blob = " ".join(str(x) for x in (labels or []) if str(x).strip())
    count = extract_cart_count(summary, xml, label_blob)
    if count is None:
        return {}
    return {"world": {"cart_count": count}, "cart_seen": True}
