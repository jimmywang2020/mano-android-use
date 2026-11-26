# Phase acceptance checklist (mano-android-use)

## Roles

- **Cursor Agent (coding):** implement, unit tests, configs, troubleshooting.
- **Human:** API keys, start MuMu/USB device, approve MCP in hosts, **sign Phase 5**.

## Phase 0 — Repo & device

- [ ] Independent env works: `uv sync --extra dev` (do **not** reuse `mano/` venv)
- [ ] MuMu on Android desktop, then `eval "$(bash scripts/mumu-adb.sh)"` (no hardcoded port / no serial in `.env`)
- [ ] `.env` has Grounder keys only (from `.env.example`)

**Human:** start MuMu, create `.env` with keys  
**Cursor:** scaffold + install help

## Phase 1 — L0

```bash
cd /Users/wangjinxiang/Desktop/Projects/mano-android-use
eval "$(bash scripts/mumu-adb.sh)"
uv run mau doctor
uv run mau ready
uv run mau observe
```

- [ ] doctor ok
- [ ] observe prints `tree_compact` + `summary`, `screenshot_for_host: false`
- [ ] `runs/<id>/journal.jsonl` created

## Phase 2 — Safety

```bash
uv run pytest -q tests/test_safety.py
```

- [ ] unit tests green
- [ ] (optional) live block evidence on a checkout-looking screen

## Phase 3 — Grounder

```bash
eval "$(bash scripts/mumu-adb.sh)"
export MAU_GROUNDER_MODEL=gui-plus-2026-02-26
export MAU_GROUNDER_API_KEY=...
uv run mau observe
uv run mau propose "点击搜索框"

export MAU_GROUNDER_MODEL=glm-4.6v-flash
export MAU_GROUNDER_BASE_URL=https://open.bigmodel.cn/api/paas/v4
export MAU_GROUNDER_API_KEY=...
uv run mau propose "点击搜索框"
```

- [ ] gui-plus parseable action
- [ ] glm-4.6v-flash parseable action

## Phase 4 — MCP

Cursor UI（2026）：**Customize → MCPs → New MCP Server**（不是只在旧 Settings 里找）。

- [ ] Workspace = `mano-android-use`；MCP command = `scripts/mau-mcp-with-mumu.sh`
- [ ] Customize → Connected 列表出现 `mano-android-use`
- [ ] Agent 能调 `doctor` / `observe`；默认 observe 不塞大图给宿主
- [ ] Codex（可稍后）：`examples/mcp.codex.toml.example`

## Phase 5 — Host acceptance (first release gate)

- [ ] **Cursor** one short no-Pack task (human)
- [ ] **Codex** one short no-Pack task (human)
- [ ] Payment/submit blocked or avoided
- [ ] journal under `runs/`
- [ ] Host default path did not stream every screenshot to the orchestrator

**Sign-off**

| Host | Date | Result | Notes |
|------|------|--------|-------|
| Cursor | | | |
| Codex | | | |

## Phase 5.1 — Host TaskState resume + recipe gates (mau memory wave)

Code + unit coverage landed (`task_patch`, `progress_json`, `forbid_labels`, DiDi
production plans). Fill the human/MCP rows when re-verified on a live Host.

- [x] `android_run` / `android_run_plan` always return `task_patch` (`mau.task_patch.v1`)
- [x] MCP/CLI accept `progress_json` / `--progress-json` (OR-seed); plan OR-merges `plan_progress`
- [x] `forbid_labels` / `success_forbid_labels` / `--success-forbid-label` block search-sheet false GOAL
- [x] Production DiDi plans: `didi-airport-carpool-vs-special.json` (+ fengye aligned); fixture marked
- [x] **M4 DONE evidence:** Meituan terminal `labels_all` includes `去结算`+`已添加`; dual-drink plan; `world_evidence.cart_count` suggest; unit false-GOAL on search-only name (`tests/test_world_evidence.py`, [`recipes/meituan.md`](recipes/meituan.md))
- [x] **M5 KPIs (unit):** `cost_report.kpis` / `mau kpi` expose `guard_noop`, `redo_same_act_class`, `l0_as_main_loop_share_pct` (`tests/test_kpi.py`)
- [x] **MCP live:** short run → merge `task_patch` → resume with `progress_json`, omit `package=`, `cold_start=false`
- [x] **Host sign-off:** SlotSpec/plan 跑通美团双品 + 滴滴生产 plan；查 `mau kpi`（redo 低、无支付、无冷启主路径）
- [x] **Optional:** `MAU_OBSERVE_BACKEND=u2` same airport plan vs ADB (observe cost only) — live runs used u2 already (`ready.observe_backend=u2`)
- [x] Host reports `cost_report.narrative` after each run
- [x] **Optional live:** lemon-tea / dual-drink plan terminal requires cart world evidence (not search list) — Host `find`「去结算」+「已添加2件」; compact digest alone missed bottom bar

| Check | Date | Result | Notes |
|-------|------|--------|-------|
| MCP TaskState resume | 2026-11-24 | PASS | Settings cold → WLAN resume: `progress_json` kept `completed_slots`; `omit_package`/`cold_start=false`; `l0_share=0`. Runs `20261124-145902-633fe6` → `…-fde36e` |
| Recipe gate (airport plan) | 2026-11-24 | PASS* | DiDi `didi-airport-carpool-vs-special`: A+B `GOAL_REACHED`; B vetoed「请输入终点」false GOAL. C tree-shortcut into「代叫」→ `NEED_HUMAN` (SafetyGateway; no call/pay). Host `find` still saw「未拼成」+「一口价」. `mau kpi` redo=0 l0=0. Run `20261124-150521-c09d27` |
| U2 opt-in (optional) | 2026-11-24 | PASS | Session already on u2; Meituan+DiDi plans observed via u2 |
| Meituan dual-drink Host | 2026-11-24 | PASS* | Plan A GOAL / B STUCK (digest truncated); Host resume+L0「选规格」纠偏；Guard deny×2 on「去结算」; `find` 已添加2件+去结算 stop-before-pay. KPIs: plan redo=3 then resume redo=0 deny=2 l0=0. Runs `…-abcccb` / `…-f02922` / `…-0b95d1` |
| Phase N label_index + safe shortcut | 2026-11-24 | PASS* | N0–N4 unit; CLI+MCP DiDi A/B/C GOAL no 代叫. **Meituan:** `label_index` tech PASS — verify run `154326-13f566` digest misses 去结算/已添加 but check matches (XML+shot: cart badge 1 + 去结算, 规格弹层仍开). **Dual-drink plan NOT PASS** — `154056-51197c` A/B real (进店+加1杯); C/D instant GOAL on same「已添加1件」screen (weak `labels_any`); never 2 SKUs. |

## Phase O — Host Continuity (A short runs + B lost-MCP)

See [`docs/plan-next.md`](plan-next.md) Phase O. A = prevent fat MCP; B = recover after `-32001`.

- [x] **O0** Contract in plan-next + playbook「A vs B」
- [x] **O1** Dual-drink C/D gates require「已添加2件」; unit `test_dual_drink_one_item_screen_fails_c_and_d`
- [x] **O2** tips / MCP `android_run_plan` docstring / agent rule: Cursor → N× short `android_run`
- [x] **O3** `mau slot-next` / MCP `slot_peek` (landed with Phase P4)
- [x] **O4** `resume_from_run` (CLI+MCP; journal → draft TaskState; no GOAL-count→cart_count; also scans `step-*.xml`)
- [x] **O5** Rule 2b / playbook point at `resume_from_run`
- [x] **O6 Live:** dual-drink via short runs → 已添加2件+去结算; TIME_BUDGET short resume (A); CLI `resume_from_run` on cart=2. DiDi short stages: reuse N5 PASS (not re-run 2026-11-26).

| Check | Date | Result | Notes |
|-------|------|--------|-------|
| O1 unit gates | 2026-11-26 | PASS | 1-item summary fails C/D; 2-item passes |
| O4 resume_from_run unit | 2026-11-26 | PASS | `tests/test_resume_from_run.py` (+ XML fallback) |
| O6 Meituan dual short-run | 2026-11-26 | PASS | N× short `android_run` (not fat plan). B `141333-093ba2` cart=1; C `141657-e0fbc6` cart=2; D `141727-4f393d` labels_all 去结算+已添加2件. Host `find` confirmed badge+去结算. Stop-before-pay. Mid C STUCK on 1-item correctly (O1 gate held). |
| O6 lost-MCP / TIME_BUDGET resume | 2026-11-26 | PASS* | A `140740-46ca77` TIME_BUDGET → short resume omit package → GOAL `8a525c`/进 LINLEE. CLI `resume_from_run` on C run → cart_count=2 from XML (journal compact missed badge). **MCP tool `resume_from_run` not in Cursor catalog after reload** — use CLI until Host re-discovers tools. |
| O6 DiDi short stages | 2026-11-26 | SKIP | Reuse Phase N DiDi MCP PASS; not re-run this session. |

## Phase P — Cut spin (wrong-page / soft-gate / dull hints)

See [`docs/plan-next.md`](plan-next.md) Phase P.

- [x] **P0** Contract: plan-next + playbook「spin budget」+ this table
- [x] **P1** Dual-drink A: no bare「点菜」; menu evidence; `A2_open_menu`; unit `test_dual_drink_store_header_diancai_not_a_done`
- [x] **P2** SKU-first acquire hints; rule/tips STUCK → find/`slot_peek` → replace hints
- [x] **P3** `tree_shortcut` miss (no screen change / Guard NO_OP) → same-step VLM; unit + KPI `tree_shortcut_miss`
- [x] **P4** `mau slot-next` / MCP `slot_peek` (O3)
- [x] **P5 Live:** dual-drink N× short; mau ≪ 5.5min; no false 1-item PASS (2026-11-26 reload)

| Check | Date | Result | Notes |
|-------|------|--------|-------|
| P1–P4 unit | 2026-11-26 | PASS | world_evidence / host_slots / run_loop / resume_from_run / guard / kpi (52) |
| P5 Meituan dual re-measure | 2026-11-26 | PASS* | **Mechanics OK / SKU intent miss.** Reload MCP. A `152528`→**爷爷不泡茶** (not LINLEE); A2 `152714` GOAL+`tree_shortcut_miss`; B `152804`→Host find 1件; C `153212` GOAL 34s; D `153300` 去结算+已添加2件. mau≈3.7min≪5.5. **Actual cart SKUs: 兰香青柠 + 青提柠檬水** — not recipe `柠檬茶`+`奶茶` (C never added 奶茶). Gate「2件+停支付前」成立；配方品类意图未验收。 |

## Phase 6 — B-path `android_run(goal)` (no LangGraph)

```bash
eval "$(bash scripts/mumu-adb.sh)"
uv run pytest -q tests/test_run_loop.py
uv run mau run "打开设置" --max-steps 8
```

- [x] unit tests green
- [x] CLI `mau run` returns a terminal status (`GOAL_REACHED` / `NEED_HUMAN` / `BLOCKED_BY_POLICY` / `STUCK` / `BUDGET_EXCEEDED` / `ERROR`)
- [x] MCP tool `android_run` listed after reconnect (host can call same loop)
- [x] Payment/submit still stops the loop (`NEED_HUMAN` / `BLOCKED_BY_POLICY`) — Airbnb 预订页 `NEED_HUMAN`，未点击

## Phase 7 — Agent tips, playbook, screen preflight (mau only)

```bash
uv run pytest -q tests/test_display_tips.py tests/test_run_loop.py
uv run mau ready   # expect tips[], screen, text_backend
```

### Phase 7.1 — mau runtime

- [x] `ready` JSON includes `screen`, `text_backend`, non-empty `tips[]` (playbook + conditional IME/screen)
- [x] MCP `ready` / `android_run` / `launch_app` docstrings mention package= vs browser+中文 and AdbKeyboard
- [x] `android_run` with screen still off after wake → `NEED_HUMAN` + `tips` (unit: `test_screen_off_need_human`)
- [x] Live (optional): `mau ready` on phone shows `screen.awake` true when unlocked

### Phase 7.2 — docs + Cursor rule

- [x] [`docs/agent-playbook.md`](agent-playbook.md) present and linked from README
- [x] [`.cursor/rules/mau-android-agent.mdc`](../.cursor/rules/mau-android-agent.mdc) `alwaysApply: true`

### Phase 7.3 — mano Core (deferred)

**Do not start** until ≥2 Consumers need the same primitive.

| Gate | When to open Core PR |
|------|----------------------|
| Action aliases (`system_button_press`) | mau mapping insufficient / other Consumer duplicates it |
| Wake primitive in Core Adb | mau `display.ensure_awake` reused elsewhere and diverging |

Until then: wake/tips stay in **mano-android-use** only.

## Phase 8 — `success_check` verifier (no Pack)

```bash
uv run pytest -q tests/test_success_check.py
# Live sample (phone/MuMu + 携程 installed):
# see docs/examples/ctrip-beijing-homestay.md
```

- [x] Unit: early-stop when check satisfied; terminate veto when not
- [x] CLI/MCP expose `--success-package` / `--success-label*` / `success_labels_*`
- [x] Live (optional): 携程搜北京民宿≈400/天 → `GOAL_REACHED` + `success_verdict.ok`（9 步至含「北京」+「民宿」检索页；默认只验 summary）

## Phase 9 — Staged `android_run_plan` (generic A/B/C)

```bash
uv run pytest -q tests/test_run_plan.py
export MANO_DEVICE_SERIAL=<serial>
uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json
```

- [x] Unit: load Ctrip plan; stop on mid-stage failure
- [x] CLI `run-plan` + MCP `android_run_plan`
- [x] Live: Ctrip plan reaches stage **C**（summary 含 `¥400-...` 价带筛选/列表态）
- [x] Meituan 粿条 plan JSON exists as same-pattern twin (live optional)
- [x] PlanState continuity: later stages get `goal_context` (completed + last_summary + do-not-redo); unit `test_plan_injects_continuity_context`; live Ctrip A→B→C with `plan_context_injected` on B/C

## Phase 10 — Default-path shrink (Host goal; mau loop; L0 execute)

```bash
uv run pytest -q tests/test_apply_action.py tests/test_run_loop.py tests/test_display_tips.py
```

- [x] Shared `apply_action` used by `android_run` (+ propose execute when allowed)
- [x] `propose_action(execute=true)` / `mau propose --execute` deprecated unless `MAU_ALLOW_PROPOSE_EXECUTE=1`
- [x] Journal/execution `via`: `android_run` | `propose_execute` | `l0_direct`
- [x] Playbook + Cursor rule + README tool groups; `docs/eval-golden.md`
- [x] Optional `stuck_same_summary` on `android_run` (default **3**; `0` = off)

See [`docs/plan-next.md`](plan-next.md) for memory / TaskState / recipe-gate Done rows.

## Later

- Phase 11+: Pack crystal / WeChat / cloud device
- Optional: `mau eval`, `run-plan --from-stage`, MCP `agent|debug` profile
