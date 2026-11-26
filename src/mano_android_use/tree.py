"""Compact accessibility-tree views for host observe (no screenshot by default)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable

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


def _row_from_node(node: ET.Element) -> dict[str, Any] | None:
    text = normalize_text(node.attrib.get("text", ""))
    desc = normalize_text(node.attrib.get("content-desc", ""))
    rid = node.attrib.get("resource-id", "")
    clickable = node.attrib.get("clickable") == "true"
    clazz = (node.attrib.get("class", "") or "").rsplit(".", 1)[-1]
    if not (text or desc or clickable or rid):
        return None
    bounds = node.attrib.get("bounds", "")
    center = _center(bounds)
    left, top, right, bottom = parse_bounds(bounds) if bounds else (0, 0, 0, 0)
    return {
        "class": clazz,
        "text": text or None,
        "desc": desc or None,
        "resource_id": rid or None,
        "package": _node_package(node) or None,
        "clickable": clickable,
        "bounds": bounds or None,
        "center": list(center) if center else None,
        "top": int(top),
        "bottom": int(bottom),
        "left": int(left),
        "right": int(right),
        "width": max(0, int(right) - int(left)),
        "height": max(0, int(bottom) - int(top)),
    }


def iter_interesting_nodes(
    xml: str,
    *,
    package: str | None = None,
    skip_packages: frozenset[str] | None = None,
    prefer_foreground: bool = True,
) -> list[dict[str, Any]]:
    """All interesting nodes (no truncation). Foreground package nodes first."""
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
        row = _row_from_node(node)
        if row is None:
            continue
        if prefer_foreground and fg and row.get("package") and row["package"] != fg:
            secondary.append(row)
        else:
            primary.append(row)
    return primary + secondary


def compact_nodes(
    xml: str,
    *,
    max_nodes: int = 80,
    package: str | None = None,
    skip_packages: frozenset[str] | None = None,
    prefer_foreground: bool = True,
) -> list[dict[str, Any]]:
    """Return a truncated list of interesting UI nodes for the host LLM.

    Document-order prefix — suitable for **summary / Host observe**, not for
    success_check truth. Prefer :func:`label_index` for gate / needle recall.

    Skips ``com.android.systemui`` (and related) so ColorOS status-bar icon
    content-desc does not crowd digests. When ``prefer_foreground`` and
    ``package`` are set, nodes from other apps are deprioritized.
    """
    if max_nodes <= 0:
        return []
    # Preserve historical early-break behaviour: stop once primary fills.
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
        row = _row_from_node(node)
        if row is None:
            continue
        # Drop geometry extras for compact host payload parity with older rows.
        slim = {
            k: row[k]
            for k in (
                "class",
                "text",
                "desc",
                "resource_id",
                "package",
                "clickable",
                "bounds",
                "center",
            )
        }
        if prefer_foreground and fg and node_pkg and node_pkg != fg:
            secondary.append(slim)
        else:
            primary.append(slim)
        if len(primary) >= max_nodes:
            break
    if len(primary) >= max_nodes:
        return primary[:max_nodes]
    need = max_nodes - len(primary)
    return primary + secondary[:need]


def _screen_height(nodes: list[dict[str, Any]]) -> int:
    bottom = 0
    for n in nodes:
        try:
            bottom = max(bottom, int(n.get("bottom") or 0))
        except (TypeError, ValueError):
            continue
    return bottom or 2400


def _band_for_top(top: int, height: int) -> str:
    if height <= 0:
        return "mid"
    y = max(0, int(top))
    if y < height * 0.33:
        return "top"
    if y >= height * 0.66:
        return "bottom"
    return "mid"


def _node_label(n: dict[str, Any]) -> str:
    return str(n.get("text") or n.get("desc") or "").strip()


def label_index(
    xml: str,
    *,
    package: str | None = None,
    max_labels: int = 96,
    per_band: int = 36,
    shell_quota: int = 12,
    needles: Iterable[str] | None = None,
    skip_packages: frozenset[str] | None = None,
) -> list[str]:
    """High-recall labels for success_check (not Host summary).

    - Prefer nodes with text/content-desc (shell clickable/rid get a small quota).
    - Stratify by y-band (top / mid / bottom) so cart/fare bars survive deep trees.
    - Force-keep any label that contains a ``needles`` substring.
    """
    if max_labels <= 0:
        return []
    nodes = iter_interesting_nodes(
        xml, package=package, skip_packages=skip_packages, prefer_foreground=True
    )
    if not nodes:
        return []

    height = _screen_height(nodes)
    needle_list = [str(n).strip() for n in (needles or []) if str(n).strip()]
    out: list[str] = []
    seen: set[str] = set()

    def _push(label: str) -> bool:
        lab = label[:40]
        if not lab or lab in seen:
            return False
        seen.add(lab)
        out.append(lab)
        return len(out) >= max_labels

    # 1) Needle force-keep (full scan, text/desc only).
    for n in nodes:
        lab = _node_label(n)
        if not lab:
            continue
        if any(nd in lab for nd in needle_list):
            if _push(lab):
                return out

    # 2) Text/desc stratified by band.
    band_counts = {"top": 0, "mid": 0, "bottom": 0}
    for n in nodes:
        lab = _node_label(n)
        if not lab:
            continue
        band = _band_for_top(int(n.get("top") or 0), height)
        if band_counts[band] >= per_band:
            continue
        if _push(lab):
            return out
        band_counts[band] += 1

    # 3) Small shell quota (clickable / rid without label) — rare, for completeness.
    shells = 0
    for n in nodes:
        if shells >= shell_quota:
            break
        if _node_label(n):
            continue
        if not (n.get("clickable") or n.get("resource_id")):
            continue
        rid = str(n.get("resource_id") or "").rsplit("/", 1)[-1]
        if not rid:
            continue
        if _push(f"#{rid}"):
            return out
        shells += 1

    return out


def screen_digest_labels(
    xml: str,
    *,
    package: str | None = None,
    max_labels: int = 24,
    max_nodes: int = 120,
) -> list[str]:
    """Foreground-filtered labels for **signatures / Host digest** (document-order).

    Do not use for success_check — use :func:`label_index` instead.
    """
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


def resolve_tap_target(
    xml: str,
    query: str,
    *,
    package: str | None = None,
    limit: int = 8,
) -> dict[str, Any] | None:
    """Pick a safe tap for ``query``.

    Prefer a **clickable** hit whose text/desc/rid contains ``query``. Else climb
    to the smallest clickable ancestor that **fully contains the label bounds**.
    Reject wide+tall bottom chrome (``operation_view`` / 代叫) that does not own
    the query — those often overlap car-row label centers.
    """
    q = (query or "").strip()
    if not q:
        return None
    nodes = iter_interesting_nodes(xml, package=package)
    if not nodes:
        return None

    height = _screen_height(nodes)
    width = max((int(n.get("right") or 0) for n in nodes), default=1080) or 1080

    labeled: list[dict[str, Any]] = []
    for n in nodes:
        blob = " ".join(
            str(x)
            for x in (n.get("text"), n.get("desc"), n.get("resource_id"))
            if x
        )
        if q in blob:
            labeled.append(n)
        if len(labeled) >= limit:
            break
    if not labeled:
        return None

    def _owns_query(n: dict[str, Any]) -> bool:
        blob = " ".join(
            str(x)
            for x in (n.get("text"), n.get("desc"), n.get("resource_id"))
            if x
        )
        return q in blob

    def _is_bottom_chrome(n: dict[str, Any]) -> bool:
        """Wide AND tall strip in the lower half — DiDi operation_view / 代叫."""
        if not n.get("clickable"):
            return False
        w = int(n.get("width") or 0)
        h = int(n.get("height") or 0)
        top = int(n.get("top") or 0)
        return (
            w >= int(width * 0.4)
            and h >= int(height * 0.10)
            and top >= int(height * 0.50)
        )

    def _contains_bounds(outer: dict[str, Any], inner: dict[str, Any]) -> bool:
        return (
            int(outer.get("left") or 0) <= int(inner.get("left") or 0)
            and int(outer.get("top") or 0) <= int(inner.get("top") or 0)
            and int(outer.get("right") or 0) >= int(inner.get("right") or 0)
            and int(outer.get("bottom") or 0) >= int(inner.get("bottom") or 0)
        )

    clickable_labeled = [n for n in labeled if n.get("clickable") and n.get("center")]
    seed = clickable_labeled[0] if clickable_labeled else next(
        (n for n in labeled if n.get("center")), None
    )
    if seed is None:
        return None

    target = seed
    if not seed.get("clickable"):
        containers = [
            n
            for n in nodes
            if n.get("clickable") and _contains_bounds(n, seed)
        ]
        containers.sort(
            key=lambda n: int(n.get("width") or 0) * int(n.get("height") or 1)
        )
        chosen = None
        for n in containers:
            if _owns_query(n):
                chosen = n
                break
        if chosen is None:
            for n in containers:
                if not _is_bottom_chrome(n):
                    chosen = n
                    break
        if chosen is None:
            return None
        target = chosen

    if _is_bottom_chrome(target) and not _owns_query(target):
        return None
    rid = str(target.get("resource_id") or "")
    if "operation_view" in rid and not _owns_query(target):
        return None
    if "代叫" in _node_label(target) and q not in "代叫":
        return None

    center = target.get("center") or seed.get("center")
    if not isinstance(center, list) or len(center) < 2:
        return None
    return {
        "query": q,
        "x": int(center[0]),
        "y": int(center[1]),
        "hit": {
            k: target.get(k)
            for k in (
                "class",
                "text",
                "desc",
                "resource_id",
                "package",
                "clickable",
                "bounds",
                "center",
            )
        },
    }
