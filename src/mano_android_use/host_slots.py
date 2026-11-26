"""Host-side SlotSpec thin lib (Phase M3).

Orchestration stays on the Host: pick the next unfinished slot, build
``android_run`` args, and on DONE merge ``completed_slots`` / ``world`` /
``policy`` (hints replacement is implicit — each slot carries its own hints).

App-agnostic: Meituan vs DiDi differ only by SlotSpec / plan data — no
``if package == meituan`` branches here. mau Guard still enforces ``policy``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .progress import normalize_progress, or_merge_progress

DEFAULT_BANNED_HINTS_ON_ACQUIRE_DONE = ("已添加", "去结算", "马上抢", "支付", "提交订单")


@dataclass
class SlotSpec:
    """One subgoal slot for Host routing."""

    id: str
    goal: str
    depends_on: list[str] = field(default_factory=list)
    done_when: dict[str, Any] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)
    forbid_when_done: dict[str, Any] = field(default_factory=dict)
    affordances: list[str] = field(default_factory=list)
    package: str | None = None
    max_steps: int = 10
    cold_start: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "goal": self.goal,
            "max_steps": self.max_steps,
        }
        if self.depends_on:
            out["depends_on"] = list(self.depends_on)
        if self.done_when:
            out["done_when"] = dict(self.done_when)
        if self.hints:
            out["hints"] = list(self.hints)
        if self.forbid_when_done:
            out["forbid_when_done"] = dict(self.forbid_when_done)
        if self.affordances:
            out["affordances"] = list(self.affordances)
        if self.package:
            out["package"] = self.package
        if self.cold_start:
            out["cold_start"] = True
        return out

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "SlotSpec":
        sid = str(raw.get("id") or raw.get("name") or "").strip()
        goal = str(raw.get("goal") or "").strip()
        if not sid or not goal:
            raise ValueError(f"SlotSpec missing id/goal: {raw!r}")
        done = raw.get("done_when") or raw.get("success_check") or {}
        if not isinstance(done, dict):
            done = {}
        hints = raw.get("hints") or raw.get("tree_hints") or []
        if isinstance(hints, str):
            hints = [p.strip() for p in hints.split(",") if p.strip()]
        depends = raw.get("depends_on") or []
        if isinstance(depends, str):
            depends = [p.strip() for p in depends.split(",") if p.strip()]
        forbid = raw.get("forbid_when_done") or {}
        if not isinstance(forbid, dict):
            forbid = {}
        afford = raw.get("affordances") or []
        if isinstance(afford, str):
            afford = [p.strip() for p in afford.split(",") if p.strip()]
        pkg = raw.get("package")
        return cls(
            id=sid,
            goal=goal,
            depends_on=[str(x).strip() for x in depends if str(x).strip()],
            done_when=dict(done),
            hints=[str(x).strip() for x in hints if str(x).strip()],
            forbid_when_done=dict(forbid),
            affordances=[str(x).strip() for x in afford if str(x).strip()],
            package=str(pkg).strip() if pkg else None,
            max_steps=max(1, int(raw.get("max_steps") or 10)),
            cold_start=bool(raw.get("cold_start")),
        )


@dataclass
class SlotGraph:
    """Ordered slot list + metadata (still Host-owned)."""

    id: str
    slots: list[SlotSpec] = field(default_factory=list)
    description: str = ""

    def by_id(self) -> dict[str, SlotSpec]:
        return {s.id: s for s in self.slots}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "slots": [s.to_dict() for s in self.slots],
        }
        if self.description:
            out["description"] = self.description
        return out


@dataclass
class AndroidRunArgs:
    """Host-ready android_run parameters (MCP / CLI)."""

    goal: str
    max_steps: int = 10
    tree_hints: list[str] = field(default_factory=list)
    success_check: dict[str, Any] = field(default_factory=dict)
    progress: dict[str, Any] = field(default_factory=dict)
    package: str | None = None
    cold_start: bool = False
    omit_package: bool = True
    slot_id: str = ""

    def to_mcp_arguments(self) -> dict[str, Any]:
        """Flatten for MCP ``android_run`` tool arguments."""
        args: dict[str, Any] = {
            "goal": self.goal,
            "max_steps": int(self.max_steps),
            "cold_start": bool(self.cold_start and not self.omit_package),
            "progress_json": json.dumps(
                normalize_progress(self.progress), ensure_ascii=False
            ),
        }
        if self.tree_hints:
            args["tree_hints"] = ",".join(self.tree_hints)
        else:
            args["tree_hints"] = ""
        sc = self.success_check or {}
        if sc.get("package"):
            args["success_package"] = str(sc["package"])
        any_labs = sc.get("labels_any") or []
        all_labs = sc.get("labels_all") or []
        forbid = sc.get("forbid_labels") or sc.get("require_absent") or []
        if any_labs:
            args["success_labels_any"] = ",".join(str(x) for x in any_labs)
        if all_labs:
            args["success_labels_all"] = ",".join(str(x) for x in all_labs)
        if forbid:
            args["success_forbid_labels"] = ",".join(str(x) for x in forbid)
        if self.package and not self.omit_package:
            args["package"] = self.package
        return args

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "goal": self.goal,
            "max_steps": self.max_steps,
            "tree_hints": list(self.tree_hints),
            "success_check": dict(self.success_check),
            "progress": normalize_progress(self.progress),
            "package": self.package,
            "cold_start": self.cold_start,
            "omit_package": self.omit_package,
            "mcp_arguments": self.to_mcp_arguments(),
        }


def completed_slot_ids(progress: dict[str, Any] | None) -> list[str]:
    prog = normalize_progress(progress)
    raw = prog.get("completed_slots") or []
    return [str(x).strip() for x in raw if str(x).strip()]


def next_slot(
    graph: SlotGraph | list[SlotSpec],
    progress: dict[str, Any] | None = None,
) -> SlotSpec | None:
    """First slot whose deps are done and id is not yet in ``completed_slots``."""
    slots = graph.slots if isinstance(graph, SlotGraph) else list(graph)
    done = set(completed_slot_ids(progress))
    for slot in slots:
        if slot.id in done:
            continue
        deps = [d for d in slot.depends_on if d]
        if all(d in done for d in deps):
            return slot
    return None


def on_done(
    progress: dict[str, Any] | None,
    slot: SlotSpec,
    *,
    sku_keys: list[str] | None = None,
    cart_count: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge DONE evidence: completed_slots + forbid_when_done → policy/world.

    Host should call this after ``GOAL_REACHED`` (or Host ``find`` verify) for
    ``slot``, then pass the result as the next ``progress_json``.
    """
    patch: dict[str, Any] = {"completed_slots": [slot.id]}
    fw = dict(slot.forbid_when_done or {})
    policy: dict[str, Any] = {}
    world: dict[str, Any] = {}
    banned_acts = fw.get("banned_act_classes") or []
    banned_hints = fw.get("banned_hint_labels") or []
    if banned_acts:
        policy["banned_act_classes"] = list(banned_acts)
    if banned_hints:
        policy["banned_hint_labels"] = list(banned_hints)
    skus = [str(x).strip() for x in (sku_keys if sku_keys is not None else fw.get("sku_keys") or []) if str(x).strip()]
    if skus:
        world["sku_keys"] = skus
    count = cart_count if cart_count is not None else fw.get("cart_count")
    if count is not None:
        try:
            world["cart_count"] = int(count)
        except (TypeError, ValueError):
            pass
    if policy:
        patch["policy"] = policy
    if world:
        patch["world"] = world
        if "cart_count" in world or skus:
            patch["cart_seen"] = True
    if extra:
        patch = or_merge_progress(patch, extra)
    return or_merge_progress(progress, patch)


def build_android_run_args(
    slot: SlotSpec,
    progress: dict[str, Any] | None = None,
    *,
    force_package: bool = False,
) -> AndroidRunArgs:
    """Build next ``android_run`` call; always uses **this slot's** hints (replace)."""
    prog = normalize_progress(progress)
    done = completed_slot_ids(prog)
    # Warm package only for the first slot (or explicit force / cold_start).
    use_package = bool(slot.package) and (
        force_package or slot.cold_start or not done
    )
    return AndroidRunArgs(
        goal=slot.goal,
        max_steps=slot.max_steps,
        tree_hints=list(slot.hints),
        success_check=dict(slot.done_when or {}),
        progress=prog,
        package=slot.package if use_package else None,
        cold_start=bool(slot.cold_start and use_package),
        omit_package=not use_package,
        slot_id=slot.id,
    )


def slots_from_plan_stages(
    stages: list[dict[str, Any]],
    *,
    linear_depends: bool = True,
) -> list[SlotSpec]:
    """Convert ``android_run_plan`` stages → SlotSpecs (optional linear depends_on)."""
    out: list[SlotSpec] = []
    prev_id = ""
    for raw in stages:
        if not isinstance(raw, dict):
            continue
        data = dict(raw)
        if linear_depends and prev_id and "depends_on" not in data:
            data["depends_on"] = [prev_id]
        # Map plan field names
        if "done_when" not in data and "success_check" in data:
            data["done_when"] = data.get("success_check")
        if "hints" not in data and "tree_hints" in data:
            data["hints"] = data.get("tree_hints")
        slot = SlotSpec.from_mapping(data)
        out.append(slot)
        prev_id = slot.id
    return out


def load_slot_graph(path: str | Path) -> SlotGraph:
    """Load a SlotGraph JSON (``slots`` array) or a run-plan JSON (``stages``)."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"slot graph must be a JSON object: {p}")
    gid = str(raw.get("id") or p.stem)
    desc = str(raw.get("description") or "")
    if isinstance(raw.get("slots"), list):
        slots = [SlotSpec.from_mapping(x) for x in raw["slots"] if isinstance(x, dict)]
    elif isinstance(raw.get("stages"), list):
        slots = slots_from_plan_stages(raw["stages"], linear_depends=True)
    else:
        raise ValueError(f"no slots/stages in {p}")
    return SlotGraph(id=gid, slots=slots, description=desc)


def host_step(
    graph: SlotGraph | list[SlotSpec],
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience: ``{slot, args, done}`` for the next Host MCP call."""
    slot = next_slot(graph, progress)
    if slot is None:
        return {
            "done": True,
            "slot": None,
            "args": None,
            "progress": normalize_progress(progress),
        }
    args = build_android_run_args(slot, progress)
    return {
        "done": False,
        "slot": slot.to_dict(),
        "args": args.to_dict(),
        "progress": normalize_progress(progress),
    }


def suggested_find_needles(slot: SlotSpec) -> list[str]:
    """Labels Host should ``find`` before the next short run / after STUCK."""
    dw = slot.done_when or {}
    out: list[str] = []
    seen: set[str] = set()
    for key in ("labels_all", "labels_any"):
        raw = dw.get(key) or []
        if isinstance(raw, str):
            raw = [p.strip() for p in raw.split(",") if p.strip()]
        for item in raw:
            lab = str(item).strip()
            if lab and lab not in seen:
                seen.add(lab)
                out.append(lab)
    return out


def slot_peek(
    graph: SlotGraph | list[SlotSpec],
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase P4 / O3: next-slot args + suggested ``find`` needles (read-only).

    After STUCK / TIME_BUDGET: Host should ``find(suggested_find)``, replace
    ``tree_hints`` if the page is wrong, then short ``android_run`` from ``args``.
    """
    step = host_step(graph, progress)
    if step.get("done"):
        return {
            **step,
            "suggested_find": [],
            "tip": "All slots complete — verify with find then stop-before-pay.",
        }
    slot_raw = step.get("slot") or {}
    # Rebuild SlotSpec for needle helper (slot dict already normalized).
    slot = SlotSpec.from_mapping(slot_raw) if isinstance(slot_raw, dict) else None
    needles = suggested_find_needles(slot) if slot else []
    return {
        **step,
        "suggested_find": needles,
        "tip": (
            "After STUCK/TIME_BUDGET: find(suggested_find) → replace tree_hints "
            "if page wrong → short android_run from args (omit package if warm)."
        ),
    }
