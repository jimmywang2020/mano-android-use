"""Optional external success verifier for android_run (Muse-style checker).

Model ``terminate:success`` is only a candidate; package/label assertions can
veto or confirm. Also used to early-stop when the screen already matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tree import screen_digest_labels


@dataclass
class SuccessCheck:
    """Declarative screen assertions (recipe gate).

    - ``package``: foreground package must equal this (exact).
    - ``labels_any``: at least one substring must appear in the search blob.
    - ``labels_all``: every substring must appear (prefer for terminal stages).
    - ``forbid_labels`` / ``require_absent``: none of these substrings may appear
      (e.g. ``请输入终点`` so dest-name hits on the search sheet cannot pass).
    - ``use_xml``: if True, search full accessibility XML (noisy; can false-hit
      buried promo nodes).
    - ``use_foreground_tree``: if True (default), also search systemui-filtered
      compact labels from XML so ColorOS status-bar noise cannot hide real UI.
      Ignored when ``use_xml`` is True (full XML already covers it).
    """

    package: str | None = None
    labels_any: list[str] = field(default_factory=list)
    labels_all: list[str] = field(default_factory=list)
    forbid_labels: list[str] = field(default_factory=list)
    use_xml: bool = False
    use_foreground_tree: bool = True

    def is_empty(self) -> bool:
        return (
            not self.package
            and not self.labels_any
            and not self.labels_all
            and not self.forbid_labels
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.package:
            out["package"] = self.package
        if self.labels_any:
            out["labels_any"] = list(self.labels_any)
        if self.labels_all:
            out["labels_all"] = list(self.labels_all)
        if self.forbid_labels:
            out["forbid_labels"] = list(self.forbid_labels)
        if self.use_xml:
            out["use_xml"] = True
        if not self.use_foreground_tree:
            out["use_foreground_tree"] = False
        return out

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "SuccessCheck | None":
        if not raw:
            return None
        package = raw.get("package")
        labels_any = raw.get("labels_any") or raw.get("labels") or []
        labels_all = raw.get("labels_all") or []
        forbid = (
            raw.get("forbid_labels")
            or raw.get("require_absent")
            or raw.get("labels_forbid")
            or []
        )
        if isinstance(labels_any, str):
            labels_any = [p.strip() for p in labels_any.split(",") if p.strip()]
        if isinstance(labels_all, str):
            labels_all = [p.strip() for p in labels_all.split(",") if p.strip()]
        if isinstance(forbid, str):
            forbid = [p.strip() for p in forbid.split(",") if p.strip()]
        use_fg = raw.get("use_foreground_tree")
        check = cls(
            package=str(package).strip() if package else None,
            labels_any=[str(x) for x in labels_any if str(x).strip()],
            labels_all=[str(x) for x in labels_all if str(x).strip()],
            forbid_labels=[str(x) for x in forbid if str(x).strip()],
            use_xml=bool(raw.get("use_xml")),
            use_foreground_tree=True if use_fg is None else bool(use_fg),
        )
        return None if check.is_empty() else check


@dataclass
class SuccessVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "reasons": self.reasons}
        if self.matched:
            out["matched"] = list(self.matched)
        return out


def _search_blob(
    check: SuccessCheck,
    *,
    package: str,
    summary: str,
    xml: str,
) -> str:
    blob = summary or ""
    if check.use_xml and xml:
        return f"{blob}\n{xml}"
    if check.use_foreground_tree and xml:
        fg = (package or check.package or "").strip() or None
        labels = screen_digest_labels(xml, package=fg, max_labels=40, max_nodes=160)
        if labels:
            blob = f"{blob}\n" + " ".join(labels)
    return blob


def evaluate_success(
    check: SuccessCheck | None,
    *,
    package: str = "",
    summary: str = "",
    xml: str = "",
) -> SuccessVerdict:
    """Return ok=True when check is None/empty or all assertions hold."""
    if check is None or check.is_empty():
        return SuccessVerdict(True, [])

    blob = _search_blob(check, package=package, summary=summary, xml=xml)
    reasons: list[str] = []
    matched: list[str] = []

    def _present(needle: str) -> bool:
        return needle in blob

    if check.package:
        if (package or "").strip() != check.package.strip():
            reasons.append(
                f"package want={check.package!r} got={package!r}"
            )

    for needle in check.labels_all:
        if not _present(needle):
            reasons.append(f"labels_all missing {needle!r}")
        else:
            matched.append(needle)

    if check.labels_any:
        hit = next((n for n in check.labels_any if _present(n)), None)
        if hit is None:
            reasons.append(
                "labels_any none of "
                + ",".join(repr(n) for n in check.labels_any)
            )
        else:
            matched.append(hit)

    for needle in check.forbid_labels:
        if _present(needle):
            reasons.append(f"forbid_labels present {needle!r}")

    return SuccessVerdict(ok=not reasons, reasons=reasons, matched=matched)


def progress_from_verdict(
    check: SuccessCheck | None,
    verdict: SuccessVerdict | None,
) -> dict[str, Any]:
    """Merge-OR progress bits from a successful (or partial) check."""
    out: dict[str, Any] = {}
    if not check or check.is_empty() or not verdict:
        return out
    if verdict.ok:
        out["goal_matched"] = True
    for lab in verdict.matched or []:
        key = f"saw:{lab}"
        out[key] = True
        # Common task bits for Host TaskState
        if lab in {"元", "一口价", "预估", "到手约"} or "元" in lab or "一口价" in lab:
            out["fare_seen"] = True
        if lab in {"加入购物车", "去结算", "结算", "购物车"}:
            out["cart_seen"] = True
    return out
