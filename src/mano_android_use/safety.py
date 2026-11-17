"""Safety gateway: block payment / submit actions before they hit ADB."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any


# Heuristic UI / intent phrases (zh + en). Expand via env or code as needed.
# Prefer multi-char / intent phrases. Bare "支付" false-positives on ColorOS
# Settings rows like「钱包与支付」and must not stop normal phone navigation.
DEFAULT_BLOCK_PATTERNS: tuple[str, ...] = (
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
    "Confirm purchase",
    "Buy now",
    "Checkout",
)


def sanitize_semantic_hint(
    hint: str,
    *,
    patterns: tuple[str, ...] = DEFAULT_BLOCK_PATTERNS,
    max_len: int = 120,
) -> str:
    """Strip payment/submit phrases from action hints (e.g. goals that say 不要立即支付).

    UI dumps are still checked in full by ``check_action`` / ``screen_looks_dangerous``.
    """
    text = hint or ""
    for p in sorted((x for x in patterns if x), key=len, reverse=True):
        text = text.replace(p, " ")
    text = re.sub(r"不要\s*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[: max(0, int(max_len))]


@dataclass
class SafetyDecision:
    allow: bool
    code: str = "OK"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"allow": self.allow, "code": self.code, "reason": self.reason}


class SafetyGateway:
    """Rule brain: independent of Pack and of the host LLM."""

    def __init__(
        self,
        *,
        block_patterns: tuple[str, ...] | None = None,
        package_allowlist: set[str] | None = None,
    ) -> None:
        patterns = block_patterns if block_patterns is not None else DEFAULT_BLOCK_PATTERNS
        self._block_re = re.compile("|".join(re.escape(p) for p in patterns if p))
        if package_allowlist is None:
            raw = os.getenv("MAU_PACKAGE_ALLOWLIST", "").strip()
            package_allowlist = {p.strip() for p in raw.split(",") if p.strip()} or None
        self.package_allowlist = package_allowlist

    def check_package(self, package: str) -> SafetyDecision:
        if self.package_allowlist and package and package not in self.package_allowlist:
            return SafetyDecision(
                False,
                "BLOCKED_BY_POLICY",
                f"package {package!r} not in allowlist",
            )
        return SafetyDecision(True)

    def check_action(
        self,
        action: dict[str, Any],
        *,
        package: str = "",
        ui_blob: str = "",
        semantic_hint: str = "",
    ) -> SafetyDecision:
        pkg = self.check_package(package)
        if not pkg.allow:
            return pkg

        kind = str(action.get("action") or action.get("type") or "")
        button = str(action.get("button") or action.get("text") or "").upper()
        # Always allow leaving / going home even on payment screens.
        if kind in {"system_button", "key"} and button in {"BACK", "HOME"}:
            return SafetyDecision(True)

        # Goals often say「不要立即支付」; strip payment phrases from the hint only.
        # Full ui_blob (not a short prefix) — payment strings often appear late in XML.
        hint = sanitize_semantic_hint(semantic_hint or "")
        hay = " ".join(
            [
                kind,
                str(action.get("text") or ""),
                str(action.get("button") or ""),
                hint,
                ui_blob,
            ]
        )
        if self._block_re.search(hay):
            return SafetyDecision(
                False,
                "BLOCKED_BY_POLICY",
                "matched payment/submit heuristic; refusing device action",
            )
        return SafetyDecision(True)

    def screen_looks_dangerous(self, ui_blob: str) -> SafetyDecision:
        if ui_blob and self._block_re.search(ui_blob):
            return SafetyDecision(
                False,
                "NEED_HUMAN",
                "screen text suggests payment/submit UI; host should stop or ask human",
            )
        return SafetyDecision(True)
