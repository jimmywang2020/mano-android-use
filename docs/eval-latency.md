# Eval: latency under same conditions

Measure wall-clock and cost for mau + mano Core after latency-oriented
changes. Same device, same model (`gui-plus-2026-02-26`), record `run_id`.

Requires mano **≥ v0.1.3** (capture modes); prefer **≥ v0.1.4** (compressed dump).

## Prep

```bash
cd /path/to/mano-android-use
eval "$(bash scripts/resolve-adb-serial.sh)"
uv sync --extra dev
uv run mau ready
```

Restart MCP after mau upgrades. On `TIME_BUDGET`, resume **without** `package=`.

## Cases

| # | Goal template (no payment button words) | Expect |
|---|-------------------------------------------|--------|
| L1 | 美团外卖搜「双皮奶」，选冷的一份加购；停在购物车即可 | 加购成功；可停在差起送；无开局 `BLOCKED_BY_POLICY` |
| L2 | 店内已有双皮奶详情：选规格冷 → 加购 | 少误 `unchanged_recover` BACK；有 `act_grace` 时点空不立刻 BACK |
| L3 | 续跑短 goal（omit package） | journal `launch` 非 cold（若带 package 则为 warm/already_foreground） |

## Record

- `run_id` / wall clock (journal first→last `ts_ms`)
- `cost_report.narrative`, `by_phase.observe` (screenshot_ms / xml_ms / by_mode)
- counts: `unchanged_recover`, `BLOCKED_BY_POLICY`, MCP `android_run` rounds
- whether dump degrade / compressed dump appeared in journal

## Pass line (vs pre-change baseline on same phone)

- Wall P50 ↓ ≥25% on L1/L2 (3 runs), **or**
- Mis-BLOCKED from goal payment words = 0, **and** non-type false BACK ↓ clearly
- Single-step observe >60s rare; dump fail degrades or fails fast instead of eating full MCP wall
