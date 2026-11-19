# mau next development plan (active)

**North star:** Host picks goal/plan; mau orchestrates; Grounder sees screenshots; L0 sole execute.

## Status

| Phase | Status |
|-------|--------|
| A Docs / rule / tool narrative | Done |
| B `apply_action` + deprecate propose execute + `via` | Done |
| C Reduce empty spinning (`stuck_same_summary`, playbook) | Done — default `stuck_same_summary=3`; playbook + act grace |
| D Golden eval doc | Done (`docs/eval-golden.md`); `mau eval` CLI optional later |
| E Acceptance Phase 0–5 / Host sign-off | Open — human Cursor/Codex rows; see `docs/acceptance.md` Phase 5 / 5.1 |
| F Local step trace (timing + tokens) | Done — `android_run_step` journal + `trace.json` + `mau trace` |
| G MCP soft wall budget + L0/propose spans | Done — `TIME_BUDGET` / `continue_hint`; `propose_step` / `l0_step` + `by_via` |
| H Unchanged-screen + tree-first vision gating | Done — `tree_hints` / quoted labels → `tree_shortcut`; `docs/eval-vision-gating.md` |
| I Structured run memory (cross-stage progress, ResumeSpec always, Grounder instruction, evidence_refs) | Done — `ea1fb08` wave |
| J Host TaskState (`task_patch` + `progress_json`) | Done — `913d00f`; MCP resume drill verified |
| K Recipe gates (`forbid_labels` / production DiDi plans) | Done — `d0d90ae` |
| L Optional U2 observe backend | Done (opt-in) — default remains ADB; `docs/eval-latency.md` |

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
- Totals include `by_via`; CLI: `mau trace [runs/<id>]` (table with `via`) or `--json`.
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
