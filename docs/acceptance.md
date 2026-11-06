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

## Later

- Phase 10+: Pack crystal / WeChat / cloud device
