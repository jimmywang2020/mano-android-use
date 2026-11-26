# Agent playbook — mano-android-use

How Cursor / Codex (or any MCP host) should drive this project. Runtime copy also
appears in `ready.tips` and MCP tool descriptions.

**Principle:** Host picks **goal/plan**; mau **orchestrates** the loop; Grounder
**sees screenshots**; **L0** is the only path that hits the device.

## Always

1. Call `doctor` then `ready` before a long task. Read `tips[]`, `screen`, `text_backend`,
   `observe_backend`.
2. Wireless debug **ports change**. Prefer MCP command `scripts/mau-mcp-with-mumu.sh` (auto-resolves via `resolve-adb-serial.sh`); do not pin a dead `ip:port` in MCP env. CLI: `eval "$(bash scripts/resolve-adb-serial.sh)"`.
3. Device must be **awake and unlocked**. `android_run` sends one `KEYCODE_WAKEUP`; it does **not** unlock.
4. Public entry for developers: root [`README.md`](../README.md) / [`README.zh-CN.md`](../README.zh-CN.md)
   (resume, gates, U2, CLI/MCP flags). This playbook remains the Host operating manual.

## Default path (multi-step)

```text
ready → (launch_app | android_run package=…) → short android_run × N
         (CLI / short plans only) → android_run_plan
```

| Goal | Tool |
|------|------|
| Health / tips | `ready` |
| One-shot UI goal | **`android_run`** (+ optional `success_check`) |
| Long / multi-stage **in Cursor** | **N× short `android_run`** via SlotSpec (`host_slots` / `docs/examples/slots/`) |
| Long job **CLI** or already-short plan | `mau run-plan` / MCP `android_run_plan` (each stage still ~90s soft budget) |
| Debug journal / lost MCP | `journal_tail` (+ Phase O `resume_from_run` when available) |

Do **not** chain `propose_action` → `tap` (or `propose_action(execute=true)`) as the main loop.
That duplicates mau’s B-path and causes long Host round-trips / empty spinning.

`propose_action(execute=true)` is **deprecated** (requires `MAU_ALLOW_PROPOSE_EXECUTE=1`).

### A vs B — Host continuity (Phase O)

| | **A — short runs** | **B — journal → ResumeSpec** |
|--|--------------------|------------------------------|
| Job | **Prevent** Cursor `-32001` on multi-stage | **Recover** when `task_patch` never arrived |
| Default? | **Yes** for Cursor Meituan/DiDi multi-slot | Only after timeout / empty tool result |
| Memory | Merge each `task_patch` into TaskState | Rebuild progress from journal + `find` (件数), then short resume |

Do **not** treat A and B as the same fix: splitting stages does not replace lost-MCP
rebuild; journal rebuild does not make fat `android_run_plan` safe under Cursor.

### Spin budget (Phase P)

O6 retro: most wall time was **wrong-page / soft-gate / dull-hint** spin, not VLM itself.
Keep soft MCP wall + unchanged skip + tree-first — fix the gates:

| Do | Don't |
|----|--------|
| Enter-store DONE = menu evidence（选规格 / 请输入商品名 / cart） | Bare「点菜」tab as A DONE |
| Optional `A2_open_menu` when store chrome lacks specs | Burn acquire stage on store header |
| Acquire `tree_hints` **SKU-first** then 选规格 | Inherit bare「选规格」across SKUs |
| After STUCK/`TIME_BUDGET`: `find` / `slot_peek` → replace hints → short run | Reopen same dull-hint `android_run` |
| Expect `tree_shortcut_miss` → same-step VLM | Treat white taps as progress |

CLI/MCP: `mau slot-next <slots.json> [--progress-json …]` / `slot_peek`.

### MCP soft budget + ResumeSpec (avoid Host `-32001`)

MCP `android_run` defaults to **short** calls (`max_steps=10`, wall soft-budget ~**90s**). When the
budget is hit (or `STUCK`), mau returns `TIME_BUDGET` / `STUCK` with `cost_report` +
`continue_hint` (alias **`resume`** — structured ResumeSpec) instead of hanging until the
Host times out empty.

**Host resume = fill the form**, do not rewrite from chat prose:

1. Read **`task_patch`** (stable merge blob) or `resume` / `continue_hint` **before**
   `cost_report.narrative` (always present; `next_actor=done` on `GOAL_REACHED`, else `host`).
2. If `next_actor=host`, call `android_run` with `resume.do` fields: same `goal` (or
   refine only if `progress` says so), **`omit package=`** (`do.omit_package=true`),
   `cold_start=false`, keep `tree_hints` / `success_check` from `do`, and pass
   **`progress_json`** = `JSON.stringify(TaskState.progress)` so mau OR-seeds
   `fare_seen` / `goal_matched` (mau does **not** persist Host TaskState).
3. Honor `dont[]`: no `HOME`, no `force_stop` / cold `launch_app`, no
   `rewrite_goal_from_scratch`, no `propose_action` main loop.
4. Merge `task_patch` into Host TaskState across MCP calls (OR-merge `progress` /
   `plan_progress`; replace `resume` / `screen_digest` / `evidence_refs` / `status`).
   Helper shape: `merge_task_state(state, task_patch)` in `run_loop` (copy logic into
   Host if needed). Shape example: [`examples/task-state.example.json`](examples/task-state.example.json).

- Very long jobs: prefer CLI `mau run` / `mau run-plan` (no MCP soft budget by default), or
  **multiple short MCP `android_run` calls** (safer under Cursor `-32001` than one fat
  `android_run_plan` that outlives the Host request timeout).
- **Goal wording:** do not put payment/submit button copy in the goal (e.g. avoid「立即支付」);
  prefer「停在确认页 / 不要付款」. Meituan-class flows → short stages (搜 → 规格加购 → 可选凑单).
- **Budgets:** keep MCP defaults short; set `max_steps` **per stage**. Do **not** lengthen one
  `android_run` to replace staging. Optional later: expose `wall_budget_ms` (deferred).

### Lost MCP response (`-32001` / empty timeout) — rebuild then ResumeSpec

When Cursor kills the tool call, mau on-device may **still finish** the current loop and write
`runs/<id>/journal.jsonl`. There is **no** `task_patch` in the Host chat — you must rebuild.

**Do this in order (Meituan dual-drink example):**

1. **Locate checkpoint**  
   - Prefer MCP/CLI **`resume_from_run`** (optional `slots_path` for dual-drink slots) →
     `draft_progress` + `mcp_hint` + `warnings` / `needs_confirm`.  
   - Fallback: `journal_tail(n=30)` or newest `runs/<id>/journal.jsonl` + last
     `step-*.png` / grep XML for `已添加` / `去结算`.
2. **Semantic status (not “GOAL count”)**  
   - Trust `draft_progress.world.cart_count` only when warnings say it came from a11y;
     still confirm with `find` when unsure.  
   - `已添加1件` → only slot B (first SKU) may be done; **C/D are not done**.  
   - `已添加2件` + `去结算` → verify slot may run.  
   - Do **not** treat `goal_reached_stop_count` / N× `GOAL_REACHED` as dual-drink success.
3. **Write Host TaskState.progress** (OR-merge bits you trust after confirming draft), e.g. after B only:
   ```json
   {
     "completed_slots": ["A_enter_store", "B_add_lemon_tea"],
     "world": { "cart_count": 1, "sku_keys": ["柠檬茶"] },
     "policy": {
       "banned_hint_labels": ["已添加", "去结算", "马上抢"],
       "banned_act_classes": []
     },
     "cart_seen": true
   }
   ```
4. **Short resume** — one `android_run` for the **next** slot only:
   - omit `package=`, `cold_start=false`
   - **replace** `tree_hints` (e.g. C: `奶茶,选规格,加入购物车`)
   - tighten `success_check` (prefer `已添加2件` / Host `find` count — not bare `labels_any:已添加`)
   - `progress_json` = `JSON.stringify(TaskState.progress)`
5. **After each short return:** merge `task_patch`; `find` 已添加 / 去结算; only then advance slot.
6. **Forbidden after timeout:** HOME, cold `launch_app`, rewrite giant goal, start a new full
   `android_run_plan` from stage A, or switch the main loop to L0/`propose_action`.

Normal (non-lost) path still prefers reading **`task_patch` / `resume.do`** from the tool
return — journal rebuild is the **fallback** when that blob never arrives.

### Host anti-redo (cross-app)

Orchestration (slots / DONE / which stage next) is **Host**; mau only runs a bounded loop.
Lemon-tea retro (2026-11-24): wall-clock blowups came from **giant goals + hint misuse +
verify-via-add-loop**, not from skipping a tree-only observe.

| Do | Don't |
|----|--------|
| One stage per subgoal (enter → acquire SKU → verify cart) | One goal spanning 搜店+选品+规格+加购 |
| **Replace** `tree_hints` every stage | Inherit bare「选规格」across SKUs / stages |
| Success labels only in `success_check` | Put「已添加」「去结算」「马上抢」in `tree_hints` |
| After add looks done: **`find` / `observe` verify** | Open another add-to-cart `android_run` |
| Clear foreign cart items in a **separate** stage | Fold「清空」into the same goal as「加入购物车」 |
| Resume with `progress_json` + current stage goal | After compact, switch main loop to L0 |
| Production plan + tight gates | Fixture-loose `labels_any` as success truth |

**Hints hygiene (never shortcut-tap these):** `已添加`, `去结算`, `马上抢`, `支付`, `提交订单`,
and other terminal/payment copy. Use them in `success_check` / Host `find` only.

**Add-to-cart miss:** Meituan「加入购物车」text is often non-clickable — L0-correct by tapping
the clickable ancestor `ViewGroup`, not as a new multi-step run.

**Verify-only:** prefer Host `find`（品名 +「去结算」/「已添加N件」）. If a plan stage must run,
use **empty** `tree_hints` and terminal **`labels_all`: `去结算` + `已添加`** (world-state) plus
品名 `labels_any` — see `C_verify_cart` /
[`meituan-lemon-tea-cart.json`](examples/plans/meituan-lemon-tea-cart.json) and dual-SKU
[`meituan-dual-drink-cart.json`](examples/plans/meituan-dual-drink-cart.json). Recipe:
[`recipes/meituan.md`](recipes/meituan.md).

**DONE evidence (M4):** search/menu **product name alone must not GOAL**. Add stages succeed
on `已添加`/`去结算`, not menu「到手约」. mau may suggest `progress.world.cart_count` from
「已添加N件」a11y; Host still authors `sku_keys`. No price-band UNSAT in mau.

Phase M: [`plan-next.md`](plan-next.md) — M0–M5 landed. After a SKU is in cart, Host should
seed `progress_json` with `world.sku_keys` + optional `policy.banned_act_classes` /
`banned_hint_labels` so Guard can NO_OP redo `选规格`/`加入购物车` (see **Guard** below).

### Host SlotSpec thin lib (M3)

Prefer reusable slot routing over ad-hoc chat staging:

```python
from mano_android_use.host_slots import load_slot_graph, next_slot, on_done, build_android_run_args

graph = load_slot_graph("docs/examples/slots/meituan-dual-drink.slots.json")
progress = {}
slot = next_slot(graph, progress)
args = build_android_run_args(slot, progress)   # slot's own tree_hints only
# MCP: android_run(**args.to_mcp_arguments())
progress = on_done(progress, slot)              # completed_slots + forbid_when_done → policy/world
```

- **`next_slot`**: first unfinished slot whose `depends_on` ⊆ `completed_slots`
- **`on_done`**: OR-merge evidence; next call automatically uses the **next** slot’s hints (replace)
- **Same API** for Meituan / DiDi — examples under [`examples/slots/`](examples/slots/)
- Plans still work: `load_slot_graph("…/meituan-lemon-tea-cart.json")` maps `stages` → linear slots

### KPIs (M5)

After runs, check anti-redo health (also embedded in `cost_report.kpis` / narrative):

```bash
uv run mau kpi runs/<id>          # table
uv run mau kpi runs/<id> --json
uv run mau trace runs/<id>        # timings + KPI block
```

| KPI | Meaning (lower/higher) |
|-----|------------------------|
| `redo_same_act_class` | Same `open_spec`/`confirm_add`+target executed again → want **low** |
| `guard_noop` / `guard_deny` | Guard short-circuits → **noop>0** after Host seeded `world`/`policy` is healthy |
| `acquire_after_cart` | Acquire taps after cart evidence → want **low** (verify-via-add smell) |
| `l0_as_main_loop_share_pct` | L0 spans vs android_run → want **low** (Host not driving with L0) |
| `android_run_rounds` | Per run_dir ≈1; Host session sum of short MCP rounds |

### Guard (M2, shared tree_shortcut + VLM)

Before every device tap from `android_run`, mau classifies an **ActClass** and consults
Host `progress`:

| Rule | Effect |
|------|--------|
| `hint` ∈ `policy.banned_hint_labels` | Soft deny (`skip_reason=guard_deny`); hint also filtered from tree-first |
| `act_class` ∈ `policy.banned_act_classes` | Soft deny (`guard_deny`) |
| `open_spec` / `confirm_add` + `target_key` ∈ `world.sku_keys` | **NO_OP** (`guard_noop`) — no tap |
| `target_key=unknown` | Never false-idempotent NO_OP (only Safety + explicit bans) |
| Payment / submit UI | Existing `SafetyGateway` → `BLOCKED_BY_POLICY` / `NEED_HUMAN` |

ActClass ids Host may ban: `open_spec`, `confirm_add`, `type_query`, `open_cart`,
`checkout`, … `target_key` is resolved from hint/text, or from goal when **exactly one**
`world.sku_keys` entry appears there. mau does **not** invent SKUs from the screenshot.

### GoalCard shape (Host TaskState)

Treat each task as a card mau can consume via `android_run` / `plan_json` stages.
Every `android_run` / `android_run_plan` return includes **`task_patch`**
(`schema: mau.task_patch.v1`) for Host merge — mau never writes Host disk.

| Field | Role |
|-------|------|
| `intent` / `goal` | What to achieve (no payment button copy) |
| `params` | Dest / SKU / city… |
| `stop_when` / `success_check` | Package + labels. Default scans **`label_index`** (y-banded, text-first, needle force-keep) — **not** the Host `compact_nodes` document-order prefix. Prefer **`labels_all`** on terminal stages; use **`forbid_labels`** (e.g. `请输入终点`) so search-sheet dest hits cannot pass |
| `forbidden` | Payment / submit / cold relaunch |
| `hints` / `tree_hints` | Stable **clickable** a11y for tree-shortcut. Verify-only stages: omit product-row labels (e.g. DiDi「特价拼车」); prefer category tabs. Shortcut rejects bottom chrome overlays (代叫 / `operation_view`) |
| `progress` | OR-merge facts; seed next call via `progress_json` (see **Progress contract** below) |
| `resume` | Last ResumeSpec — preferred next call |
| `screen_digest` / `evidence_refs` | Last filtered labels + shot/xml paths (debug / audit) |

### Progress contract (M1)

Host owns TaskState; mau OR-seeds / returns the same shape. Prefer structured fields
over only `saw:…` bits when staging anti-redo:

| Field | Merge | Role |
|-------|-------|------|
| `completed_slots[]` | ordered union | Slot ids Host marks DONE (`enter_store`, `add:鸭屎香`, …) |
| `world.cart_count` | max int (0 kept) | Cart size — Host and/or mau suggest from「已添加N件」 |
| `world.sku_keys[]` | ordered union | SKUs already in cart (**Host-authored**; mau does **not** auto-infer) |
| `policy.banned_act_classes[]` | ordered union | For M2 Guard (e.g. `add_same_sku`); stored+prompted in M1 |
| `policy.banned_hint_labels[]` | ordered union | Labels Host must not put in / shortcut on (e.g. `已添加`, `去结算`) |
| Legacy `fare_seen` / `cart_seen` / `goal_matched` / `saw:X` | truthy OR | Still valid; `cart_seen` or `world.cart_count>0` triggers progress-hold (no suicide BACK) |

`merge_task_state` / `parse_progress_json` / plan cross-stage merge all use this OR-merge.
Example blob: [`examples/task-state.example.json`](examples/task-state.example.json).
**Do not** expect mau to fill `sku_keys` from UI in M1 — Host sets them after `find` / stage success.

**Recipe gate discipline:** memory resumes work; **gates define success**. Do not use
loose dest-name `labels_any` as production stop conditions. Preferred DiDi plan:
[`examples/plans/didi-airport-carpool-vs-special.json`](examples/plans/didi-airport-carpool-vs-special.json)
（`role: production`）。Fixture only:
[`examples/plans/ab-didi-xiangmihu-fare.json`](examples/plans/ab-didi-xiangmihu-fare.json)
（故意松，易假完成）。Recipe: [`recipes/didi.md`](recipes/didi.md).

### Full observe + skip VLM when possible

Inside `android_run` (default `stuck_same_summary=3`, override with `0` / env `MAU_STUCK_SAME_SUMMARY`):

1. **Every step: one `full` observe** (`capture_mode=full`: screenshot+XML in one window) →
   screen signature = `package` + summary + **systemui-filtered foreground tree fingerprint**
   (so ColorOS status-bar noise cannot pin an unchanged signature).
2. **`success_check` runs before unchanged recover** (`label_index` by default — cart/fare bars survive deep headers;
   opt into full XML with `use_xml=true`). If matched → `GOAL_REACHED` without BACK.
3. If signature **unchanged** vs previous step: **do not call VLM** — first time `BACK`
   recover, then short wait, then `STUCK` + ResumeSpec. Exceptions: `act_grace` after
   type/click/swipe; **`fare_seen` / `cart_seen` progress holds** (no suicide BACK — Host
   gets ResumeSpec with progress).
4. Before VLM: try **tree-first** on the same dump — `tree_hints` and/or「quoted」labels in
   the goal; `resolve_tap_target` (clickable / ancestor, reject bottom chrome; **focus vs
   submit**: for 搜索/请输入/… prefer EditText/search-box over short Button「搜索」) →
   `via=tree_shortcut` (`grounder_ms=0`; PNG already paid this step, unused by Grounder).
5. When VLM is required: reuse the step’s PNG (no second capture). `cost_report` shows
   observe split (`screenshot_ms` / `xml_ms` / modes). Dump failures degrade full → `shot`
   or fail fast (`ERROR`) so one step cannot burn the whole MCP wall budget.

`package=` on `android_run` is **warm** by default (no force-stop if already foreground).
Use `cold_start=true` / CLI `--cold-start` / `launch_app` only for a true relaunch. On
`TIME_BUDGET` resume, omit `package=` when the app is already open.
Host should pass stable labels when known (e.g. `tree_hints=设置` or goal `打开「设置」`)
and prefer short staged goals for Meituan-class flows.
L0 MCP `observe(detail=tree|screenshot|both)` still maps to Core `tree|shot|full` for
manual/debug; `android_run` always uses `full`.

### Optional U2 observe (faster capture)

- Install: `uv sync --extra u2` (does **not** change default MCP deps).
- Enable: `MAU_OBSERVE_BACKEND=u2` (unset / `adb` = stock ADB `screencap`+`dump`).
- On U2 failure: same step falls back to ADB; journal `observe_backend=u2_fallback_adb`.
- Tap/type/swipe stay on ADB. See [`docs/eval-latency.md`](eval-latency.md) microbench gate.

Acceptance checklist: [`docs/eval-vision-gating.md`](eval-vision-gating.md).

## Open an app

| Situation | Do this |
|-----------|---------|
| Package known (e.g. 哔哩哔哩 → `tv.danmaku.bili`) | `android_run(goal=..., package="tv.danmaku.bili")` or `launch_app` |
| App on desktop, package unknown | `observe` / `find` then `tap`, or ask human for package |
| Avoid | Browser address bar + Chinese `type` just to open an installed app |

## L0 correction only

Use `observe` → `find` / `tap` / `swipe` / `type_text` / `press_button` for:

- APK install / ColorOS「继续安装」dialogs
- One-off nudge after a failed run
- Debugging coordinates

Not for multi-step product goals.

## Chinese text

- Requires OpenATX **AdbKeyboard** (`com.github.uiautomator/.AdbKeyboard`).
- If `ready.text_backend.available` is false: **launch/tap/swipe only**; do not `type_text` / goals that need typing.
- Install APK via `adb install`; ColorOS「继续安装」/防护弹窗 → `observe`+`tap` or human — **not** `android_run`.

## Safety

- Payment / submit screens → `NEED_HUMAN` or `BLOCKED_BY_POLICY`. Stop; do not force.
- Settings rows like「钱包与支付」are **not** payment (heuristic tightened in mau).
- Prefer MCP/CLI L0 (`tap` etc.) over shell `adb input tap` so safety + journal stay intact.

## Wireless phone (ColorOS example)

```bash
adb pair <配对IP>:<配对端口> <配对码>
adb connect <连接IP>:<连接端口>
export MANO_DEVICE_SERIAL=<连接IP>:<连接端口>
uv run mau ready
```

Update `~/.cursor/mcp.json` `env.MANO_DEVICE_SERIAL` the same way; bump `MCP_REV` if tools look stale.

## Cost / timing (always surface to the human)

`android_run` and `android_run_plan` JSON include **`cost_report`**:

| Field | Meaning |
|-------|---------|
| `narrative` | One-line summary — quote this to the user |
| `by_phase.observe` | ADB capture (tree/shot/full on demand); see `screenshot_ms` / `xml_ms` |
| `by_phase.grounder` | VLM propose (**only** phase that uses tokens) |
| `by_phase.act` | L0 tap / swipe / type / press |
| `by_via` | Rollup by path: `android_run` / `propose` / `l0_direct` / `propose_execute` |
| `per_step` / `stages` | Per loop step or per plan stage |

Journal span events: `android_run_step` (main KPI), plus bypass `propose_step` / `l0_step`.
`mau trace` shows the whole run_dir journal (including later L0/propose) with a `via` column.
`android_run` internal taps do **not** emit duplicate `l0_step`.

Host must report totals + which phase dominated after each run (no separate UI needed).

Each MCP `android_run` / `android_run_plan` starts a **fresh `run_id`/`run_dir`**
(`begin_run`); `cost_report` is computed from **that call’s history**, so prior tasks
on the same long-lived session do not inflate totals. Plan stages share one run_dir
but each stage’s `cost_report` stays stage-scoped; plan rollup sums stages.

Malformed VLM actions (e.g. `click` without coordinates) are **skipped and retried**,
not an immediate stage `ERROR`.

## success_check (prefer for “正确”)

Pass `success_package` / `success_labels_any` / `success_labels_all` /
`success_forbid_labels`（plan JSON: `forbid_labels` / `require_absent`）so
`GOAL_REACHED` requires an external screen assertion, not only model terminate.

Use **narrow** labels (avoid matching too early). Terminal stages: prefer
`labels_all`. Prefer staged production plans over one huge goal / loose fixture OR
with a loose check.

Example: [docs/examples/ctrip-beijing-homestay.md](examples/ctrip-beijing-homestay.md).

## Staged plans (A/B/C) — app-agnostic

Long goals → split into stages, each with its own `goal` + `success_check` and a
modest `max_steps` (avoid burning budget on empty spinning).

Runner: `mau run-plan <plan.json>` or MCP `android_run_plan`.

| App | Plan JSON |
|-----|-----------|
| 携程北京民宿 | [examples/plans/ctrip-beijing-homestay.json](examples/plans/ctrip-beijing-homestay.json) |
| 美团粿条外卖 | [examples/plans/meituan-guotiao-takeout.json](examples/plans/meituan-guotiao-takeout.json) |

Same code path; only package / labels / goals change. Host can also call `android_run` three times by hand.
Latency / dump baseline: [`docs/eval-latency.md`](eval-latency.md).

Between stages, `PlanState` injects into the next stage prompt: completed stage ids,
last screen summary, and **do not redo completed stages** (no unnecessary relaunch /
re-select city). This is thin continuity — not a full LangGraph.

## Out of scope for mau

- Installing / approving third-party APKs as a product feature
- Pattern/password unlock
- mano Core Pack / WeChat entry (later phases)
