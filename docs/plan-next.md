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
| **Q Wall-clock hygiene (no STUCK→L0; dump137; dynamic C hints)** | **Active** — Q0–Q3 landed 2026-11-26; **Q4 live** pending |

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

## Phase P — Cut spin (wrong-page / soft-gate / dull hints) (closed*)

**Why (O6 retro):** Dual-drink mau ~5.5min of which ~1min effective add+verify; ~4.5min spin from **wrong stage page**, **soft enter gate** (`点菜` tab), **wide `tree_shortcut` hints**, **no pre-`find` before next short run**. Cross-task mechanisms; dual-drink amplifies.

| ID | Scope | Exit |
|----|--------|------|
| **P0–P5** | **Done*** | Soft A gate, SKU-first hints, shortcut→VLM, `slot_peek`, live PASS* 2026-11-26. Follow-ups → **Phase Q**. |

## Phase Q — Wall-clock hygiene (active)

**Why (P5 / 意图分流重测 2026-11-26):** A→D 墙钟 ~**5.6min**，有效 `step_ms`（A+B+C2+D）仅 ~**1.8min**。差额主要来自：

| 桶 | 大约 | 根因 |
|----|------|------|
| STUCK 后 Host **L0 连点** | ~51s + 空隙 | C1 STUCK 后 observe/tap/BACK；每次叠 **ui_dump 137** |
| **ui_dump / ui_refresh_error 137** | in-run 间隔合计 ~99s | 无线 ADB / uiautomator 重试把一步撑胖 |
| **首轮 C hint 不对** | C1 整段 ~34s+ | 店内无「奶茶」仍用配方 hint → STUCK → 再 C2 |

意图分流已单独落地（搜框 focus>submit）；本 Phase **不再做分流**。

### Success metrics（三目标）

| # | 目标 | 衡量 | 非目标 |
|---|------|------|--------|
| 1 | **完成任务** | dual-drink：`已添加2件`+`去结算`、停支付前；SKU 尽量柠檬茶+另一单杯（允许无奶茶时动态换） | 假 PASS（1 件当 2 件） |
| 2 | **降成本** | **墙钟** A→D（及 mau `Σstep_ms`）；对标上次 ~5.6min → 目标 **≲3min** 墙钟 | **不计 token** |
| 3 | **泛化** | 纪律/基建 app-agnostic；第二杯 hint **当场 find**，禁止写死店内 SKU | Meituan SM；slots 死写「林里招牌」 |

### Do / Don't

| | Do | Don't |
|--|----|-------|
| Host | STUCK/`TIME_BUDGET` → **`find` / `slot_peek` → 换 hint → 短 `android_run`** | STUCK 后 L0 连点当主路径 |
| Host | 进 C 前 `find` 可见第二杯（奶茶或另一单杯）再开 **一次** C | 为「跳过 C1」写死 SKU |
| mau | 提高 dump 成功率 / 缩短 137 重试；journal 可观测 | 失败就跳过 tree 校验（伤完成） |
| L0 | 仅 install 对话框 / 单点纠偏（如非 clickable「加入购物车」祖先） | STUCK 后连环 tap/BACK |

### Sub-phases

| ID | Scope | Exit | 对三目标 |
|----|--------|------|----------|
| **Q0 Contract** | 本节 + playbook「Wall-clock hygiene」+ acceptance Phase Q；墙钟指标不计 token | **Done** | — |
| **Q1 Host：禁 STUCK→L0** | rule / tips / playbook / recipe 硬纪律 | **Done** | 完成↑/持平；墙钟 −~70s（按上次账）；泛化强 |
| **Q2 mau：ui_dump 137** | Act 前若 observe XML 仍新鲜则 **跳过** 二次 `ui_dump`（`MAU_UI_REFRESH_MAX_AGE_MS`，默认 8s）；journal `ui_refresh_skipped` / `ui_refresh_error.code`；失败保留旧 XML（不吞成成功） | **Done**（unit）；live 减 137 见 Q4 | 完成↑；墙钟预期大降；泛化强 |
| **Q3 Host：进 C 动态 hint** | recipe/playbook：B 后 `find` → 填 C hints；禁死 SKU | **Done**（docs） | 完成持平/升；少 C1；泛化靠流程 |
| **Q4 Live re-measure** | 同机 dual-drink：禁 L0、新 dump、进 C 前 find；记录墙钟 / dump137 / C 轮数 | **Pending** | 三目标验收 |

**Order:** Q0 → Q1 ∥ Q2 → Q3 → Q4（Q1/Q2 可并行；Q3 不依赖 Q2 代码，但 live 建议三项齐）。

**Predicted wall (上次 333s 账，非承诺):**

| 组合 | 预测墙钟 |
|------|----------|
| 仅 Q1 | ~4.4min |
| 仅 Q2（保守） | ~4.1–4.4min |
| Q1+Q2 | ~2.9–3.2min |
| Q1+Q2+Q3（无 C1） | ~2.5–3.0min |

**Non-goals:** 优化 token；加长单次 `android_run`；Session TaskStore；支付自动化；把第二杯 SKU 写进 slots 死数据；关闭 tree-first / unchanged skip。

**Risks:** Q2 若「跳过失败 dump」→ shortcut 误判成功（伤目标1）— 必须修成功率而非吞错。Q3 若 Host 偷懒写死 SKU → 伤目标3 并间接伤目标1。

## Env flags

| Flag | Effect |
|------|--------|
| `MAU_ALLOW_PROPOSE_EXECUTE=1` | Allow deprecated `propose_action(execute=true)` / `mau propose --execute` |
| `MAU_OBSERVE_BACKEND=adb\|u2` | Observe path (`u2` needs `uv sync --extra u2`; fallback to ADB on failure) |
| `MAU_STUCK_SAME_SUMMARY` | Override unchanged-screen threshold when CLI/MCP leave default |
| `MAU_UI_REFRESH_MAX_AGE_MS` | Phase Q2: skip act-path `ui_dump` when `last_xml` younger than this (default `8000`; `0` = always dump) |

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
