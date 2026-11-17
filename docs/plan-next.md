# mau next development plan (active)

**North star:** Host picks goal/plan; mau orchestrates; Grounder sees screenshots; L0 sole execute.

## Status

| Phase | Status |
|-------|--------|
| A Docs / rule / tool narrative | Done (this iteration) |
| B `apply_action` + deprecate propose execute + `via` | Done (this iteration) |
| C Reduce empty spinning (`stuck_same_summary`, playbook) | Partial (`stuck_same_summary` default off; playbook narrowed) |
| D Golden eval doc | Done (`docs/eval-golden.md`); `mau eval` CLI optional later |
| E Acceptance Phase 0–5 / Codex sign-off | Open |
| F Local step trace (timing + tokens) | Done — `android_run_step` journal + `trace.json` + `mau trace` (no LangSmith) |
| G MCP soft wall budget + L0/propose spans | Done — `TIME_BUDGET` / `continue_hint`; `propose_step` / `l0_step` + `by_via` |

## Env flags

| Flag | Effect |
|------|--------|
| `MAU_ALLOW_PROPOSE_EXECUTE=1` | Allow deprecated `propose_action(execute=true)` / `mau propose --execute` |

## Trace / KPI

- Each `android_run` step logs `event=android_run_step` with `observe_ms` / `grounder_ms` / `act_ms` / token fields.
- Bypass: `propose_step` / `l0_step` (only when `via` is propose / l0_direct — not for `via=android_run`).
- On stop, rebuilds `runs/<id>/trace.json` from journal (works across `run-plan` stages + later L0/propose).
- Totals include `by_via`; CLI: `mau trace [runs/<id>]` (table with `via`) or `--json`.
- MCP: `wall_budget_ms≈90s`, default `max_steps=10` → `TIME_BUDGET` + `continue_hint` instead of Host `-32001`.
- Follow-up: if DashScope/`GuiVLM` ever stops updating client token counters, gui-plus per-step tokens may stay `0` (fields still present).

## Deferred

Pack / WeChat / cloud / iOS / MCP profile split / LangSmith (not planned; local journal is the KPI path).
