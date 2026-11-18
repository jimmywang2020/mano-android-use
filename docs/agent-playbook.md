# Agent playbook — mano-android-use

How Cursor / Codex (or any MCP host) should drive this project. Runtime copy also
appears in `ready.tips` and MCP tool descriptions.

**Principle:** Host picks **goal/plan**; mau **orchestrates** the loop; Grounder
**sees screenshots**; **L0** is the only path that hits the device.

## Always

1. Call `doctor` then `ready` before a long task. Read `tips[]`, `screen`, `text_backend`.
2. Wireless debug **ports change**. Prefer MCP command `scripts/mau-mcp-with-mumu.sh` (auto-resolves via `resolve-adb-serial.sh`); do not pin a dead `ip:port` in MCP env. CLI: `eval "$(bash scripts/resolve-adb-serial.sh)"`.
3. Device must be **awake and unlocked**. `android_run` sends one `KEYCODE_WAKEUP`; it does **not** unlock.

## Default path (multi-step)

```text
ready → (launch_app | android_run package=…) → android_run | android_run_plan
```

| Goal | Tool |
|------|------|
| Health / tips | `ready` |
| One-shot UI goal | **`android_run`** (+ optional `success_check`) |
| Long / multi-stage goal | **`android_run_plan`** (short stages + per-stage `success_check`) |
| Debug journal | `journal_tail` |

Do **not** chain `propose_action` → `tap` (or `propose_action(execute=true)`) as the main loop.
That duplicates mau’s B-path and causes long Host round-trips / empty spinning.

`propose_action(execute=true)` is **deprecated** (requires `MAU_ALLOW_PROPOSE_EXECUTE=1`).

### MCP soft budget + ResumeSpec (avoid Host `-32001`)

MCP `android_run` defaults to **short** calls (`max_steps=10`, wall soft-budget ~**90s**). When the
budget is hit (or `STUCK`), mau returns `TIME_BUDGET` / `STUCK` with `cost_report` +
`continue_hint` (alias **`resume`** — structured ResumeSpec) instead of hanging until the
Host times out empty.

**Host resume = fill the form**, do not rewrite from chat prose:

1. Read `resume` / `continue_hint` **before** `cost_report.narrative`.
2. Call `android_run` with `resume.do` fields: same `goal` (or refine only if `progress`
   says so), **`omit package=`** (`do.omit_package=true`), `cold_start=false`, keep
   `tree_hints` / `success_check` from `do`.
3. Honor `dont[]`: no `HOME`, no `force_stop` / cold `launch_app`, no
   `rewrite_goal_from_scratch`, no `propose_action` main loop.
4. Carry `progress` / `screen_digest` in Host TaskState across MCP calls.

- Very long jobs: prefer CLI `mau run` / `mau run-plan` (no MCP soft budget by default), or
  multiple short MCP stages via `android_run_plan`.
- **Goal wording:** do not put payment/submit button copy in the goal (e.g. avoid「立即支付」);
  prefer「停在确认页 / 不要付款」. Meituan-class flows → short stages (搜 → 规格加购 → 可选凑单).

### GoalCard shape (Host TaskState)

Treat each task as a card mau can consume via `android_run` / `plan_json` stages:

| Field | Role |
|-------|------|
| `intent` / `goal` | What to achieve (no payment button copy) |
| `params` | Dest / SKU / city… |
| `stop_when` / `success_check` | Package + labels (default scans **foreground tree**, not dirty summary alone) |
| `forbidden` | Payment / submit / cold relaunch |
| `hints` / `tree_hints` | Stable a11y strings for tree-shortcut |
| `progress` | OR-merge facts from mau (`fare_seen`, `goal_matched`, …) |
| `resume` | Last ResumeSpec — preferred next call |

Example DiDi fare plan: [`examples/plans/ab-didi-xiangmihu-fare.json`](examples/plans/ab-didi-xiangmihu-fare.json);
recipe notes: [`recipes/didi.md`](recipes/didi.md).

### Full observe + skip VLM when possible

Inside `android_run` (default `stuck_same_summary=3`, override with `0` / env `MAU_STUCK_SAME_SUMMARY`):

1. **Every step: one `full` observe** (`capture_mode=full`: screenshot+XML in one window) →
   screen signature = `package` + summary + **systemui-filtered foreground tree fingerprint**
   (so ColorOS status-bar noise cannot pin an unchanged signature).
2. **`success_check` runs before unchanged recover** (foreground compact labels by default;
   opt into full XML with `use_xml=true`). If matched → `GOAL_REACHED` without BACK.
3. If signature **unchanged** vs previous step: **do not call VLM** — first time `BACK`
   recover, then short wait, then `STUCK` + ResumeSpec. Exceptions: `act_grace` after
   type/click/swipe; **`fare_seen` / `cart_seen` progress holds** (no suicide BACK — Host
   gets ResumeSpec with progress).
4. Before VLM: try **tree-first** on the same dump — `tree_hints` and/or「quoted」labels in
   the goal; unique `find` hit → tap with `via=tree_shortcut` (`grounder_ms=0`; PNG already
   paid this step, unused by Grounder).
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

Pass `success_package` / `success_labels_any` / `success_labels_all` so
`GOAL_REACHED` requires an external screen assertion, not only model terminate.

Use **narrow** labels (avoid matching too early). Prefer staged plans over one huge goal
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
