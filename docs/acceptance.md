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

## Later

- Phase 7+: Pack crystal / WeChat / cloud device
