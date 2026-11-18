"""Compact accessibility-tree views for host observe (no screenshot by default)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from mano.ui_xml import normalize_text, parse_bounds

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

# ColorOS / Android status-bar noise that crowded U2 digests and broke signatures.
_SKIP_PACKAGES_DEFAULT = frozenset(
    {
        "com.android.systemui",
        "com.oplus.systemui.plugins",
    }
)


def _center(bounds: str) -> tuple[int, int] | None:
    left, top, right, bottom = parse_bounds(bounds)
    if right <= left or bottom <= top:
        return None
    return (left + right) // 2, (top + bottom) // 2


def _node_package(node: ET.Element) -> str:
    return (node.attrib.get("package") or "").strip()


def should_skip_package(
    node_pkg: str,
    *,
    skip_packages: frozenset[str] | None = None,
) -> bool:
    """Skip status-bar / system UI packages that crowd digests."""
    skip = skip_packages if skip_packages is not None else _SKIP_PACKAGES_DEFAULT
    return bool(node_pkg and node_pkg in skip)


def compact_nodes(
    xml: str,
    *,
    max_nodes: int = 80,
    package: str | None = None,
    skip_packages: frozenset[str] | None = None,
    prefer_foreground: bool = True,
) -> list[dict[str, Any]]:
    """Return a truncated list of interesting UI nodes for the host LLM.

    Skips ``com.android.systemui`` (and related) so ColorOS status-bar icon
    content-desc does not crowd digests used by summary / signature / checks.
    When ``prefer_foreground`` and ``package`` are set, nodes from other apps
    are deprioritized (collected after foreground hits fill the budget).
    """
    if not xml.strip():
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    fg = (package or "").strip() or None
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    for node in root.iter("node"):
        node_pkg = _node_package(node)
        if should_skip_package(node_pkg, skip_packages=skip_packages):
            continue
        text = normalize_text(node.attrib.get("text", ""))
        desc = normalize_text(node.attrib.get("content-desc", ""))
        rid = node.attrib.get("resource-id", "")
        clickable = node.attrib.get("clickable") == "true"
        clazz = (node.attrib.get("class", "") or "").rsplit(".", 1)[-1]
        if not (text or desc or clickable or rid):
            continue
        bounds = node.attrib.get("bounds", "")
        center = _center(bounds)
        row = {
            "class": clazz,
            "text": text or None,
            "desc": desc or None,
            "resource_id": rid or None,
            "package": node_pkg or None,
            "clickable": clickable,
            "bounds": bounds or None,
            "center": list(center) if center else None,
        }
        if prefer_foreground and fg and node_pkg and node_pkg != fg:
            secondary.append(row)
        else:
            primary.append(row)
        if len(primary) >= max_nodes:
            break
    if len(primary) >= max_nodes:
        return primary[:max_nodes]
    need = max_nodes - len(primary)
    return primary + secondary[:need]


def screen_digest_labels(
    xml: str,
    *,
    package: str | None = None,
    max_labels: int = 24,
    max_nodes: int = 120,
) -> list[str]:
    """Foreground-filtered labels for signatures and success_check blobs."""
    nodes = compact_nodes(xml, max_nodes=max_nodes, package=package)
    labels: list[str] = []
    for n in nodes:
        label = n.get("text") or n.get("desc")
        if label:
            labels.append(str(label)[:40])
        if len(labels) >= max_labels:
            break
    return labels


def summarize(package: str, nodes: list[dict[str, Any]]) -> str:
    """One-line human summary for host orchestration (no vision)."""
    labels = []
    for n in nodes:
        label = n.get("text") or n.get("desc")
        if label:
            labels.append(str(label)[:40])
        if len(labels) >= 20:
            break
    has_edit = any(n.get("class") in {"EditText", "AutoCompleteTextView"} for n in nodes)
    # Keep aligned with safety.py — avoid bare「支付」(ColorOS「钱包与支付」).
    _danger_keys = (
        "立即支付",
        "现在支付",
        "确认支付",
        "确认付款",
        "提交订单",
        "确认下单",
        "去支付",
        "收银台",
        "付款",
        "Pay now",
        "Place order",
        "Buy now",
        "Checkout",
    )
    danger = any(
        any(k in (str(n.get("text") or "") + str(n.get("desc") or "")) for k in _danger_keys)
        for n in nodes
    )
    bits = [f"package={package or 'unknown'}"]
    if has_edit:
        bits.append("has_text_field")
    if danger:
        bits.append("possible_payment_ui")
    if labels:
        bits.append("labels=[" + ", ".join(labels) + "]")
    else:
        bits.append("labels=[]")
    return "; ".join(bits)


def find_by_text(xml: str, query: str, *, limit: int = 10, package: str | None = None) -> list[dict[str, Any]]:
    """Find nodes whose text/desc/resource-id contains query (case-sensitive substring)."""
    q = query.strip()
    if not q:
        return []
    hits = []
    for node in compact_nodes(xml, max_nodes=500, package=package):
        blob = " ".join(
            str(x)
            for x in (node.get("text"), node.get("desc"), node.get("resource_id"))
            if x
        )
        if q in blob:
            hits.append(node)
        if len(hits) >= limit:
            break
    return hits
