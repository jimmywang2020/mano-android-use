# Eval: latency under same conditions

Measure wall-clock and cost for mau + mano Core after latency-oriented
changes. Same device, same model (`gui-plus-2026-02-26`), record `run_id`.

Requires mano **≥ v0.1.3** (capture modes); prefer **≥ v0.1.4** (compressed dump).
`android_run` defaults to **one `full` observe per step** (no tree→full double tax).

## Execution-layer KPIs (mau)

Do **not** use “feels like Codex Computer Use” as the bar. Prefer:

| KPI | How to read |
|-----|-------------|
| Step observe cost | `screenshot_ms` / `xml_ms` / `capture_attempt` / wall per `observe(detail=both)` |
| No double tax | journal/history: `capture_mode=full`, **no** happy-path `observe_upgrade=full_for_vlm` |
| Skip VLM when possible | `vlm_skipped`, `via=tree_shortcut` / unchanged recover |
| False BACK / BLOCKED | `act_grace` present after type/click/swipe; payment words not in `semantic_hint` |

Host wall-clock for a full Meituan order is a **joint** Host×mau metric; channel upgrades (e.g. U2) must pass **observe microbench** first.

## Prep

```bash
cd /path/to/mano-android-use
eval "$(bash scripts/resolve-adb-serial.sh)"
uv sync --extra dev
uv run mau ready
```

Restart MCP after mau upgrades (and after wireless ADB port changes). On `TIME_BUDGET`, resume **without** `package=`.

## Observe microbench (ADB baseline)

Same phone, same screen, **N≥8** samples after one warm observe. Record p50/p95 of wall, `screenshot_ms`, `xml_ms`, and `capture_attempt`. Do **not** judge a new backend by a full order wall-clock alone.

```bash
export MANO_DEVICE_SERIAL=…   # from resolve-adb-serial.sh
# Put the target app/screen in foreground, then:
uv run python - <<'PY'
import json, os, time
from pathlib import Path
from mano_android_use.session import DeviceSession

N = 8
session = DeviceSession.open(os.environ["MANO_DEVICE_SERIAL"], runs_root=Path("runs"))
session.observe(detail="both")
rows = []
for i in range(N):
    t0 = time.perf_counter()
    obs = session.observe(detail="both")
    bd = obs.get("observe_breakdown") or {}
    rows.append({
        "wall_ms": int((time.perf_counter() - t0) * 1000),
        "screenshot_ms": int(bd.get("screenshot_ms") or 0),
        "xml_ms": int(bd.get("xml_ms") or 0),
        "capture_attempt": int(bd.get("capture_attempt") or 0),
        "capture_mode": obs.get("capture_mode"),
        "package": obs.get("package"),
    })
print(json.dumps(rows, ensure_ascii=False, indent=2))
PY
```

### Snapshot (wireless phone `10.10.51.111:44543`, 2026-11-18, mau `f269f40`)

| Screen | n | wall p50 | shot p50 | xml p50 | attempts |
|--------|---|----------|----------|---------|----------|
| Settings (developer options) | 8 | **~3.9 s** | ~0.87 s | ~2.7 s | always **1** |
| Meituan home | 8 | **~21 s** | ~3.0 s | ~3.5 s | always **3** (skew/unstable retries) |

Takeaway: on Meituan-class UI the dominant cost is often **stability retries (attempt=3)**, not a single dump. Any U2/ATX spike must beat this table on the **same serial/screen** (p50 wall and attempts), without paying ADB again on the same step.

### P2 spike: U2 vs ADB (same serial, 2026-11-18)

Raw JSON: `/tmp/mau-p2-u2-vs-adb.json` (local). Method: N=8 after warm; ADB = mau `observe(detail=both)`; U2 = `screenshot()` + `dump_hierarchy()` (no mau skew loop).

| Screen | Backend | wall p50 | shot p50 | xml p50 | attempts |
|--------|---------|----------|----------|---------|----------|
| Settings | ADB | ~6.5 s | ~0.92 s | (breakdown 0 this run*) | 1 |
| Settings | **U2** | **~0.87 s** | ~0.36 s | ~0.50 s | 1 |
| Meituan home | ADB | ~8.1 s | ~1.9 s | (breakdown 0 this run*) | 1 |
| Meituan home | **U2** | **~1.76 s** | ~0.45 s | ~1.31 s | 1 |

\*ADB `xml_ms` in Core breakdown was 0 in this session while wall still included dump work — trust **wall p50** for the A/B. Earlier P1 Meituan run had wall ~21 s with `capture_attempt=3`; this P2 ADB Meituan was calmer (attempt=1).

**Gate:** U2 wall p50 is ~**7×** (Settings) / ~**4.6×** (Meituan) faster than same-day ADB full observe; attempts not worse; spike path did not chain U2→ADB on one step.

**Verdict:** microbench **passes** → optional U2 observe backend is wired in mau (see below).

### Optional U2 observe backend (productized in mau)

Default remains ADB. To use U2:

```bash
uv sync --extra u2 --extra dev
export MAU_OBSERVE_BACKEND=u2
eval "$(bash scripts/resolve-adb-serial.sh)"
uv run mau ready   # tips + observe_backend.available
```

- Journal / payload: `observe_backend=u2` or `u2_fallback_adb` (never silent).
- Act path stays ADB + safety.
- Microbench with env on should beat the ADB rows above on the same phone; `cost_report` may list `backends u2×N`.

## Cases (task-level)

| # | Goal template (no payment button words) | Expect |
|---|-------------------------------------------|--------|
| L1 | 美团外卖搜「双皮奶」，选冷的一份加购；停在购物车即可 | 加购成功；可停在差起送；无开局 `BLOCKED_BY_POLICY` |
| L2 | 店内已有双皮奶详情：选规格冷 → 加购 | 少误 `unchanged_recover` BACK；有 `act_grace` 时点空不立刻 BACK |
| L3 | 续跑短 goal（omit package） | journal `launch` 非 cold（若带 package 则为 warm/already_foreground） |
| O1 | Short Settings `android_run` + `tree_hints` | `full×N`, no `full_for_vlm`; optional `tree_shortcut` |

## Record

- `run_id` / wall clock (journal first→last `ts_ms`)
- `cost_report.narrative`, `by_phase.observe` (screenshot_ms / xml_ms / by_mode)
- counts: `unchanged_recover`, `BLOCKED_BY_POLICY`, MCP `android_run` rounds
- whether dump degrade / compressed dump appeared in journal
- for channel work: microbench JSON (settings + one Meituan screen)

## Pass line (vs pre-change baseline on same phone)

- Task L1/L2: Wall P50 ↓ ≥25% (3 runs), **or** mis-BLOCKED from goal payment words = 0 **and** non-type false BACK ↓ clearly
- Single-step observe >60s rare; dump fail degrades or fails fast instead of eating full MCP wall
- Channel (U2) gate: microbench p50 wall ↓ clearly vs table above on **both** a calm screen and Meituan; attempts not worse; no U2→ADB double capture on one step
