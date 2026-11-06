"""Optional external success verifier for android_run (Muse-style checker).

Model ``terminate:success`` is only a candidate; package/label assertions can
veto or confirm. Also used to early-stop when the screen already matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SuccessCheck:
    """Declarative screen assertions.

    - ``package``: foreground package must equal this (exact).
    - ``labels_any``: at least one substring must appear in the search blob.
    - ``labels_all``: every substring must appear.
    - ``use_xml``: if True, also search full accessibility XML (noisy; default
      False — summary only, to avoid false hits from off-screen / buried nodes).
    """

    package: str | None = None
    labels_any: list[str] = field(default_factory=list)
    labels_all: list[str] = field(default_factory=list)
    use_xml: bool = False

    def is_empty(self) -> bool:
        return not self.package and not self.labels_any and not self.labels_all

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.package:
            out["package"] = self.package
        if self.labels_any:
            out["labels_any"] = list(self.labels_any)
        if self.labels_all:
            out["labels_all"] = list(self.labels_all)
        if self.use_xml:
            out["use_xml"] = True
        return out

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "SuccessCheck | None":
        if not raw:
            return None
        package = raw.get("package")
        labels_any = raw.get("labels_any") or raw.get("labels") or []
        labels_all = raw.get("labels_all") or []
        if isinstance(labels_any, str):
            labels_any = [p.strip() for p in labels_any.split(",") if p.strip()]
        if isinstance(labels_all, str):
            labels_all = [p.strip() for p in labels_all.split(",") if p.strip()]
        check = cls(
            package=str(package).strip() if package else None,
            labels_any=[str(x) for x in labels_any if str(x).strip()],
            labels_all=[str(x) for x in labels_all if str(x).strip()],
            use_xml=bool(raw.get("use_xml")),
        )
        return None if check.is_empty() else check


@dataclass
class SuccessVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reasons": self.reasons}


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

    # Default: compact summary only (tree summarize labels). Full XML often
    # contains city names in buried/recommended nodes and false-triggers checks.
    blob = summary or ""
    if check.use_xml and xml:
        blob = f"{blob}\n{xml}"
    reasons: list[str] = []

    def _present(needle: str) -> bool:
        # Summary-only by default. Do not scan full XML for ¥ — query pages often
        # bury promotional prices and false-trigger stage C.
        return needle in blob

    if check.package:
        if (package or "").strip() != check.package.strip():
            reasons.append(
                f"package want={check.package!r} got={package!r}"
            )

    for needle in check.labels_all:
        if not _present(needle):
            reasons.append(f"labels_all missing {needle!r}")

    if check.labels_any:
        if not any(_present(n) for n in check.labels_any):
            reasons.append(
                "labels_any none of "
                + ",".join(repr(n) for n in check.labels_any)
            )

    return SuccessVerdict(ok=not reasons, reasons=reasons)
