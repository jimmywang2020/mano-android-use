# mau next development plan (active)

**North star:** Host picks goal/plan; mau orchestrates; Grounder sees screenshots; L0 sole execute.

## Status

| Phase | Status |
|-------|--------|
| A Docs / rule / tool narrative | Done |
| B `apply_action` + deprecate propose execute + `via` | Done |
| C Reduce empty spinning (`stuck_same_summary`, playbook) | Done — default `stuck_same_summary=3`; playbook + act grace |
| D Golden eval doc | Done (`docs/eval-golden.md`); `mau eval` CLI optional later |
| E Acceptance Phase 0–5 / Host sign-off | Phase 5.1 Host live filled 2026-11-24 (MCP resume + Meituan dual + DiDi airport); Phase 5 table still human-optional |
| F Local step trace (timing + tokens) | Done — `android_run_step` journal + `trace.json` + `mau trace` |
| G MCP soft wall budget + L0/propose spans | Done — `TIME_BUDGET` / `continue_hint`; `propose_step` / `l0_step` + `by_via` |
| H Unchanged-screen + tree-first vision gating | Done — `tree_hints` / quoted labels → `tree_shortcut`; `docs/eval-vision-gating.md` |
| I Structured run memory (cross-stage progress, ResumeSpec always, Grounder instruction, evidence_refs) | Done — `ea1fb08` wave |
| J Host TaskState (`task_patch` + `progress_json`) | Done — `913d00f`; MCP resume drill verified |
| K Recipe gates (`forbid_labels` / production DiDi plans) | Done — `d0d90ae` |
| L Optional U2 observe backend | Done (opt-in) — default remains ADB; `docs/eval-latency.md` |
| **M Anti-redo (Host编排 + mau Guard)** | **Done** — M0–M5 code + Host live Phase 5.1 sign-off 2026-11-24 (`docs/acceptance.md`) |
| **N Label index + safe tree_shortcut** | **Done** — N0–N5 (DiDi live GOAL 2026-11-24; Meituan via fixture+live XML) |
| **O Host Continuity (A short runs + B lost-MCP)** | **Done*** — O0–O2+O4–O6 Meituan live PASS 2026-11-26; O3 optional leftover |
| **P Cut spin (wrong-page / soft-gate / dull hints)** | **Done*** — P0–P5; live PASS* 2026-11-26 (~3.7min mau vs O6 5.5) |

## Phase M — Anti-redo (closed)

**North star unchanged.** Host owns slots/edges/DONE/hints; mau adds generic gates later.
**Anti-patterns:** giant single goal; success labels in `tree_hints`; lengthen one run instead of staging; mau Meituan state machine; UNSAT price stop (deferred).

| Sub-phase | Status | Notes |
|-----------|--------|-------|
| **M0–M5** | **Done** | See git / acceptance 5.1. Live follow-ups moved to **Phase N**. |

## Phase N — Label index + safe tree_shortcut (closed)

**Why:** Phase 5.1 showed `success_check` false-FAIL when Meituan/DiDi key labels sit below document-order `compact_nodes` budget; DiDi C then `tree_shortcut` on non-clickable「特价拼车」hit bottom `operation_view` → 代叫 → `NEED_HUMAN`.

| Sub-phase | Status | Scope / exit |
|-----------|--------|----------------|
| **N0–N4** | **Done** | Fixtures, `label_index`, wire `success_check`, safe `tree_shortcut`, DiDi C hints. |
| **N5 Live re-accept** | **Partial → O** | DiDi PASS. Dual-drink false GOAL on 1-item → **Phase O1** gates + **O6** re-sign. |

## Phase O — Host Continuity (A short runs + B lost-MCP) (closed*)

**Why:** Cursor `-32001` + Host skipping TaskState merge caused dual-drink false PASS (`154056-51197c`). Docs alone insufficient.

**Two layers (not the same bug):**

| | **A — short `android_run` default** | **B — journal → ResumeSpec** |
|--|--------------------------------------|------------------------------|
| Role | **Prevent** fat MCP wall time | **Recover** when `task_patch` never arrives |
| Happy path | N× short runs + merge `task_patch` each time | Unused |
| After `-32001` | Reduces how often B is needed | Rebuild progress from journal/`find`, then short resume |

**Shared gate:** dual-drink C/D must require **已添加2件** (not bare `labels_any:已添加`). A/B without this still false-PASS.

**Non-goals:** Session TaskStore auto-seed; auto `on_done(cart_count)` from GOAL; delete `android_run_plan`; mau Meituan SM; UNSAT.

| Sub-phase | Status | Scope / exit |
|-----------|--------|----------------|
| **O0 Contract** | **Done** | This section + playbook「A vs B」+ acceptance Phase O skeleton. |
| **O1 Dual-drink gates** | **Done** | Plan/slots C/D → `已添加2件`; unit: 1-item screen ≠ C/D DONE. |
| **O2 Short-run default** | **Done** | tips / MCP `android_run_plan` docstring / rule: Cursor multi-stage → slots short runs; plan = CLI or short plans. |
| **O3 `slot-next` (optional)** | Pending | CLI/MCP read-only next MCP args from slots+progress (no device). |
| **O4 `resume_from_run`** | **Done** | CLI+MCP code; scans journal + `step-*.xml`; never GOAL-count→cart_count. |
| **O5 Rule harden B** | **Done** | Rule 2b / playbook Lost-MCP → call `resume_from_run` first. |
| **O6 Live accept** | **Done*** | Meituan dual short-run → 2件+去结算; A TIME_BUDGET short resume; CLI resume_from_run cart=2. DiDi skipped (N5). Cursor MCP schema may omit new tool until full reconnect. |

**Priority leftover:** O3 optional; MCP reconnect so `resume_from_run` appears in Cursor tool list.

**Deferred (eval):** mau Session TaskStore — helps lost `task_patch`, amplifies false GOAL if auto-seeded; revisit only with explicit `task_begin` + no auto `on_done`.

## Phase P — Cut spin (wrong-page / soft-gate / dull hints) (active)

**Why (O6 retro):** Dual-drink mau ~5.5min of which ~1min effective add+verify; ~4.5min spin from **wrong stage page**, **soft enter gate** (`点菜` tab), **wide `tree_shortcut` hints**, **no pre-`find` before next short run**. Cross-task mechanisms; dual-drink amplifies.

**Fix only the high-ROI bucket** (do **not** kill soft wall budget / unchanged skip / tree-first entirely).

| | Do | Don't |
|--|----|-------|
| Host | Split slots; tight `done_when`; replace hints; `find` before next run | Giant goal; inherit「选规格」 |
| mau | Soft-gate hygiene helpers; shortcut miss → VLM; optional hint ban after noop | Lengthen MCP wall; Meituan SM |
| Grounder | Only when shortcut abstains / fails | Force VLM every step |
| L0 | Keep as late correction | Main loop |

### Sub-phases

| ID | Scope | Exit |
|----|--------|------|
| **P0 Contract** | This section + playbook「spin budget」; acceptance Phase P | **Done** |
| **P1 Enter-store gate** | Dual-drink **A**: no bare「点菜」; menu evidence; **A2_open_menu** | **Done** (unit) |
| **P2 Hint hygiene** | SKU-first acquire hints; rule/tips STUCK → find/`slot_peek` | **Done** |
| **P3 Shortcut fallback** | `tree_shortcut` no screen change / Guard NO_OP → VLM same step (`tree_shortcut_miss`) | **Done** (unit+KPI) |
| **P4 Preflight Host path** | `mau slot-next` / MCP `slot_peek` (O3) | **Done** |
| **P5 Live re-measure** | Dual-drink N× short; mau ≪ 5.5min; no false 1-item PASS | **Done*** (~3.7min; see acceptance) |

**Order:** P0→P1→P2→P3→P4→P5（P3/P4 可并行于 P2 后）。

**Non-goals:** raise MCP `wall_budget_ms` to “fix” spin; disable unchanged skip globally; Session TaskStore; UNSAT price; payment automation.

**Risks:** P1 tighter A → more A TIME_BUDGET (acceptable vs wrong-page B); P3 more VLM tokens on dull hints (acceptable vs white taps).

## Env flags

| Flag | Effect |
|------|--------|
| `MAU_ALLOW_PROPOSE_EXECUTE=1` | Allow deprecated `propose_action(execute=true)` / `mau propose --execute` |
| `MAU_OBSERVE_BACKEND=adb\|u2` | Observe path (`u2` needs `uv sync --extra u2`; fallback to ADB on failure) |
| `MAU_STUCK_SAME_SUMMARY` | Override unchanged-screen threshold when CLI/MCP leave default |

## Trace / KPI

- Each `android_run` step logs `event=android_run_step` with `observe_ms` / `grounder_ms` / `act_ms` / token fields.
- Bypass: `propose_step` / `l0_step` (only when `via` is propose / l0_direct — not for `via=android_run`).
- On stop, rebuilds `runs/<id>/trace.json` from journal (works across `run-plan` stages + later L0/propose).
- Totals include `by_via`; CLI: `mau trace [runs/<id>]` (table with `via` + KPI block) or `--json`.
- Anti-redo KPIs: `mau kpi [runs/<id>]` → `guard_noop`, `redo_same_act_class`, `l0_as_main_loop_share_pct`, …; also `cost_report.kpis`.
- MCP: `wall_budget_ms≈90s`, default `max_steps=10` → `TIME_BUDGET` + `task_patch` / `continue_hint` instead of Host `-32001`.
- Unchanged screen skips VLM (`vlm_skipped` / `unchanged_recover`); tree-first uses `via=tree_shortcut`.
- Follow-up: if DashScope/`GuiVLM` ever stops updating client token counters, gui-plus per-step tokens may stay `0` (fields still present).

## Still optional / deferred

| Item | Notes |
|------|-------|
| ADB same-path对照（机场 plan） | Optional latency check only |
| Host verified short rules (P2) | Manual promotion of `when` → hints; do not auto-write |
| `dest_set` / `loading` progress bits | Add when false BACK / false GOAL needs them |
| L0 → memory hints | Low ROI vs default `android_run` path |
| Pack / WeChat / cloud / iOS / MCP profile split / LangSmith | Not planned; local journal is the KPI path |
| 业务约束失败专用回传（价带/库存等 → `NEED_HUMAN`/`UNSAT` + evidence） | **记待办，暂不做**（2026-11-24 柠檬茶复盘）。先靠 Host 分 stage + 短预算；勿用加长单次 run 替代编排 |
| MCP 可选暴露 `wall_budget_ms` | 认同可做；默认仍短预算；Host 按 stage 调 `max_steps`，禁止加长一次 run 扛全单 |
| Session TaskStore（自动 merge/种子） | Phase O 非目标；见 O 节 Deferred |

## Lemon-tea retro consensus (2026-11-24)

- **full-every-step**：为消灭 tree→full 双税、保住 VLM 正确性；美团类慢病在 **步数与 Host 编排**，不在「少了一张树」。
- **预算**：默认短；Host 按 stage 设 `max_steps`；可选暴露 `wall_budget_ms`；禁止用加长一次 run 替代分 stage。
