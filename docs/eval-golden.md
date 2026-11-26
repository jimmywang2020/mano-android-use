# Golden eval tasks (mau)

Short, reproducible checks for the **declared** surface. Prefer MuMu or an unlocked phone with `MANO_DEVICE_SERIAL` set.

Principle under test: Host picks goal → mau `android_run` / `run-plan` → L0 execution (journal `via=android_run`).

## Prep

```bash
cd /path/to/mano-android-use
eval "$(bash scripts/resolve-adb-serial.sh)"   # or export MANO_DEVICE_SERIAL=…
uv run mau ready                               # screen.awake, tips[]
```

## Tasks

| # | Command | Expect |
|---|---------|--------|
| 1 | `uv run mau doctor` | `ok: true` |
| 2 | `uv run mau ready` | `ready` / tips mention default `android_run` path |
| 3 | `uv run mau run "打开设置" --max-steps 8` | terminal `GOAL_REACHED` or clear progress toward Settings; not endless propose/tap from Host |
| 4 | `uv run mau run "打开设置" --package com.android.settings --max-steps 6` | reaches Settings with fewer exploratory steps when package is valid on device |
| 5 | Payment / submit screen (manual): open a checkout-like page, then `mau run "完成支付" --max-steps 5` | `NEED_HUMAN` or `BLOCKED_BY_POLICY`; no pay tap in journal |
| 6 | Staged plan smoke (optional, app installed): `uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json` | stages progress or fail mid-stage with clear status — not silent Host tool thrash |
| 6b | DiDi production gate (optional, app + cleared history): `uv run mau run-plan docs/examples/plans/didi-airport-carpool-vs-special.json` | stages honor `forbid_labels` / C `labels_all`; no false GOAL on `请输入终点`+dest name — see [`recipes/didi.md`](recipes/didi.md) |
| 7 | After any `mau run`: inspect `runs/<id>/journal.jsonl` + `trace.json` | at least one `event=android_run_step` with ms fields; `trace.json` `totals.step_ms` ≥ 0; `mau trace runs/<id>` prints a table with `via` |
| 8 | MCP soft budget (unit / slow mock): `android_run(..., wall_budget_ms=…)` | `TIME_BUDGET` + `cost_report` + `task_patch` / `continue_hint` (not an empty Host timeout) |
| 8b | Host resume seed: `mau run ... --progress-json '{"fare_seen":true}' --wall-budget-ms …` or MCP `progress_json` | returned `progress` / `task_patch.progress` keeps seeded bits (OR-merge) |
| 8c | M1 contract seed: `--progress-json '{"completed_slots":["A"],"world":{"cart_count":1,"sku_keys":["柠檬茶"]},"policy":{"banned_hint_labels":["已添加"]}}'` | returned progress unions slots/skus; `cart_count` max; prompt/PlanState mentions completed slots / banned hints (`tests/test_progress.py`) |
| 8d | M2 Guard: seed `world.sku_keys` + tree_hints `选规格` while goal names that SKU | no device tap; journal/cost `skip_reason=guard_noop` (`tests/test_guard.py`) |
| 8e | M4 DONE gates (unit): search blob with only「柠檬茶」vs cart blob with「去结算」+「已添加」 | search fails terminal `labels_all`; cart passes (`tests/test_world_evidence.py`) |
| 8f | Optional live: `mau run-plan docs/examples/plans/meituan-lemon-tea-cart.json` (or dual-drink) | terminal stage needs cart world evidence; no false GOAL on search list — [`recipes/meituan.md`](recipes/meituan.md) |
| 8g | M3 Host slots (unit): load Meituan dual + DiDi airport SlotSpec; `next_slot` → `on_done` → hints replace | same API both apps; resume omits package (`tests/test_host_slots.py`, [`examples/slots/`](examples/slots/)) |
| 8h | M5 KPIs (unit / CLI): history with guard_noop + double open_spec; `mau kpi` | `redo_same_act_class≥1`, `guard_noop≥1`; `cost_report.kpis` present (`tests/test_kpi.py`) |
| 9 | After MCP `propose_action` / direct `tap` | journal has `propose_step` / `l0_step`; `totals.by_via` populated; `android_run` internal tap does **not** add `l0_step` |
| 10 | Vision gating device checks | See [`eval-vision-gating.md`](eval-vision-gating.md) (U1/U2/T1/T2/C1) |
| 11 | Optional U2 observe | `MAU_OBSERVE_BACKEND=u2` after `uv sync --extra u2`; `ready.observe_backend` / journal `observe_backend` — see [`eval-latency.md`](eval-latency.md) |

## Journal checks

After a `mau run`, open `runs/<id>/journal.jsonl`:

- Device acts should carry `"via": "android_run"` when coming from the loop.
- L0 MCP/CLI taps should carry `"via": "l0_direct"` and an `l0_step` span.
- `propose_action` logs `propose_step` (tokens + timing); `propose_execute` rare unless `MAU_ALLOW_PROPOSE_EXECUTE=1`.
- Loop steps should include `android_run_step` spans (`observe_ms` / `grounder_ms` / `act_ms` / tokens).
- `trace.json` / `cost_report` include `by_via` when bypass spans are present.

## Out of scope for this list

Pack, WeChat, cloud devices, unlock, APK install productization, LangSmith export.
