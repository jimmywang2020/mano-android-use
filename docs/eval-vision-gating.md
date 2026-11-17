# Eval: unchanged screen + tree-first (vision gating)

Measure whether mau skips useless VLM calls. Same device, same model
(`gui-plus-2026-02-26`), record `run_id` + `cost_report`.

## Prep

```bash
cd /path/to/mano-android-use
eval "$(bash scripts/resolve-adb-serial.sh)"
uv run mau ready
```

Optional baseline (disable gating):  
`uv run mau run "…" --stuck-same-summary 0` (no tree hints).

## Cases

| # | Command | Expect |
|---|---------|--------|
| U1 | Hard/noop goal that leaves the same screen, e.g. `mau run "点一个不存在的按钮xyz" --max-steps 8` | `vlm_skipped` ≥ 1; earlier `STUCK` than baseline; fewer `grounder_calls` / lower `grounder_ms` |
| U2 | `mau run "打开设置" --package com.android.settings --max-steps 8` | Still reachable; at most one recover; not false STUCK on progress |
| T1 | `mau run '打开「设置」' --tree-hint 设置 --max-steps 6` (or launcher with visible 设置) | Journal/`cost_report` has `via=tree_shortcut`; that step `grounder_ms=0` |
| T2 | WebView-heavy flow (e.g. Fliggy search page) without useful tree labels | Still uses VLM; no endless empty `find` loop |
| C1 | Compare U1/T1 vs baseline `cost_report` | U1/T1: lower `prompt_tokens` and/or `grounder` share; narrative mentions VLM skipped / bypass |

## Record

For each run copy:

- `run_id` / `run_dir`
- `status` / `reason`
- `cost_report.narrative`
- `cost_report.grounder_calls`, `vlm_skipped`, `by_via`
- whether `TIME_BUDGET` fired

## Pass line

- **U1:** ≥30% fewer grounder calls than baseline under the same `max_steps`, **or** clean earlier `STUCK` with `vlm_skipped` > 0.
- **T1:** ≥1 `tree_shortcut` step; total `grounder_ms` below no-hint control on the same goal.
- **U2 + T2:** no regression (completable goals still complete; vision-needed flows still call VLM).
