"""Pre-act Guard shared by tree_shortcut and VLM acts (Phase M2).

Reads Host ``progress.policy`` / ``progress.world`` only — no Meituan state machine.
Payment/submit remains ``SafetyGateway``; Guard adds anti-redo NO_OP / soft deny.
``target_key=unknown`` never gets false idempotent NO_OP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .act_class import (
    CHECKOUT,
    CONFIRM_ADD,
    OPEN_SPEC,
    UNKNOWN_TARGET,
    classify_action,
    match_sku_keys,
)
from .progress import POLICY_KEY, WORLD_KEY, normalize_progress

SKIP_GUARD_NOOP = "guard_noop"
SKIP_GUARD_DENY = "guard_deny"

CODE_OK = "OK"
CODE_NOOP = "GUARD_NOOP"
CODE_DENY = "GUARD_DENY"


@dataclass
class GuardDecision:
    allow: bool
    code: str = CODE_OK
    reason: str = ""
    act_class: str = ""
    target_key: str = UNKNOWN_TARGET
    skip_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "code": self.code,
            "reason": self.reason,
            "act_class": self.act_class,
            "target_key": self.target_key,
            "skip_reason": self.skip_reason,
        }


def _policy_lists(progress: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    prog = normalize_progress(progress)
    policy = prog.get(POLICY_KEY) if isinstance(prog.get(POLICY_KEY), dict) else {}
    banned_acts = [
        str(x).strip()
        for x in (policy.get("banned_act_classes") or [])
        if str(x).strip()
    ]
    banned_hints = [
        str(x).strip()
        for x in (policy.get("banned_hint_labels") or [])
        if str(x).strip()
    ]
    return banned_acts, banned_hints


def _world_sku_keys(progress: dict[str, Any] | None) -> list[str]:
    prog = normalize_progress(progress)
    world = prog.get(WORLD_KEY) if isinstance(prog.get(WORLD_KEY), dict) else {}
    return [str(x).strip() for x in (world.get("sku_keys") or []) if str(x).strip()]


def hint_is_banned(hint: str, banned_hint_labels: list[str]) -> str | None:
    """Return the banned label that matches ``hint``, else None."""
    text = (hint or "").strip()
    if not text:
        return None
    for ban in banned_hint_labels:
        if not ban:
            continue
        if ban in text or text in ban:
            return ban
    return None


def filter_tree_candidates(
    candidates: list[str],
    progress: dict[str, Any] | None,
) -> list[str]:
    """Drop tree_hints that Host banned (never shortcut-tap success/payment labels)."""
    _, banned_hints = _policy_lists(progress)
    if not banned_hints:
        return list(candidates)
    out: list[str] = []
    for raw in candidates:
        lab = str(raw or "").strip()
        if not lab:
            continue
        if hint_is_banned(lab, banned_hints):
            continue
        out.append(lab)
    return out


def guard_proposed_act(
    *,
    progress: dict[str, Any] | None,
    kind: str = "",
    hint: str = "",
    goal: str = "",
    action: dict[str, Any] | None = None,
) -> GuardDecision:
    """Decide whether to execute a tree_shortcut / VLM-mapped act."""
    sku_keys = _world_sku_keys(progress)
    banned_acts, banned_hints = _policy_lists(progress)
    act_class, target_key = classify_action(
        action,
        kind=kind,
        hint=hint,
        goal=goal,
        sku_keys=sku_keys,
    )

    banned_hit = hint_is_banned(hint, banned_hints)
    if banned_hit:
        return GuardDecision(
            allow=False,
            code=CODE_DENY,
            reason=f"hint matches policy.banned_hint_labels {banned_hit!r}",
            act_class=act_class,
            target_key=target_key,
            skip_reason=SKIP_GUARD_DENY,
        )

    if act_class in banned_acts:
        return GuardDecision(
            allow=False,
            code=CODE_DENY,
            reason=f"act_class {act_class!r} in policy.banned_act_classes",
            act_class=act_class,
            target_key=target_key,
            skip_reason=SKIP_GUARD_DENY,
        )

    # Idempotent add/spec only when target is a known cart SKU (never for unknown).
    if (
        act_class in {CONFIRM_ADD, OPEN_SPEC}
        and target_key != UNKNOWN_TARGET
        and match_sku_keys(target_key, sku_keys)
    ):
        return GuardDecision(
            allow=False,
            code=CODE_NOOP,
            reason=(
                f"{act_class} for target_key={target_key!r} already in world.sku_keys"
            ),
            act_class=act_class,
            target_key=target_key,
            skip_reason=SKIP_GUARD_NOOP,
        )

    # Checkout often belongs in success_check only; Host may ban it explicitly above.
    if act_class == CHECKOUT and CHECKOUT in banned_acts:
        # already handled; keep for clarity
        pass

    return GuardDecision(
        allow=True,
        code=CODE_OK,
        reason="",
        act_class=act_class,
        target_key=target_key,
        skip_reason="",
    )
