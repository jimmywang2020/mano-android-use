# Eval: unchanged screen + tree-first + full-every-step observe

Measure whether mau skips useless VLM calls while paying **one full observe per
step** (no tree→full double tax). Same device, same model (`gui-plus-2026-02-26`),
record `run_id` + `cost_report`. Requires mano **≥ v0.1.3** (`capture_observation`
modes); prefer **≥ v0.1.4** (compressed dump / warm_start).

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
| O1 | Any `android_run` (U1/T1/VLM) | Each step journal `capture_mode=full` (or modes=`[full]`); **no** `observe_upgrade=full_for_vlm` on the happy path |
| O2 | Type/click into Meituan search/spec then same summary | No immediate `unchanged_recover` BACK; journal has `act_grace` / `act_grace_skip_unchanged` (type also keeps `type_grace_*` aliases) |
| O3 | Resume `android_run` with `package=` while app foreground | Journal `launch.mode=already_foreground` or `warm` (not `cold`) unless `cold_start=true` |
| C1 | Compare U1/T1 vs baseline `cost_report` | U1/T1: lower `prompt_tokens` and/or `grounder` share; narrative mentions VLM skipped / bypass; observe still shows `screenshot_ms` + `xml_ms` per step |

## Record

For each run copy:

- `run_id` / `run_dir`
- `status` / `reason`
- `cost_report.narrative`
- `cost_report.grounder_calls`, `vlm_skipped`, `by_via`
- `by_phase.observe.screenshot_ms` / `xml_ms` / `by_mode` (when present)
- whether `TIME_BUDGET` fired

## Pass line

- **U1:** ≥30% fewer grounder calls than baseline under the same `max_steps`, **or** clean earlier `STUCK` with `vlm_skipped` > 0.
- **T1:** ≥1 `tree_shortcut` step; total `grounder_ms` below no-hint control on the same goal.
- **O1:** no tree→full double capture; modes per step are a single `full` (unless dump degrade to `shot`).
- **U2 + T2:** no regression (completable goals still complete; vision-needed flows still call VLM).
