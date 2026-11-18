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

## Same-path A/B (ADB vs U2 observe)

**Question:** On the **same** task path, does flipping only `MAU_OBSERVE_BACKEND` stably cut observe/step wall without worse outcomes?

**Fixture plan:** [`docs/examples/plans/ab-meituan-guotiao-20.json`](examples/plans/ab-meituan-guotiao-20.json)  
美团搜粿条 → 进店 → 加购约 ¥15–25 → 停在购物车/确认（不付款）。Stages A/B/C `max_steps=10` each; **tight** `success_check` (A needs `粿条`+`月售`; B `粿条`+`加入购物车`; C cart/checkout labels — not bare `配送`).

**Locks:** same `MANO_DEVICE_SERIAL`, CLI `uv run mau run-plan` (not MCP soft budget), model `gui-plus-2026-02-26`, same plan JSON, force-stop Meituan (or cold stage A) before each arm. Toggle **only** `MAU_OBSERVE_BACKEND=adb|u2`.

**Protocol** (or `bash scripts/ab-observe-backend.sh`):

```text
for pair in 1..3:
  resolve-adb-serial once per pair start
  force-stop com.sankuai.meituan
  arm1 = adb if pair odd else u2   # odd/even swap first arm
  MAU_OBSERVE_BACKEND=$arm1 uv run mau run-plan ... --model gui-plus-2026-02-26
  record; force-stop again
  MAU_OBSERVE_BACKEND=$other ...
```

Per arm record: `run_id`, wall (`time` or journal first→last `ts_ms`), `cost_report.narrative`, `by_phase.observe`, `by_backend` (must be pure — **void + rerun** if `u2_fallback_adb`), outcome (cart OK? pay UI? shop/item).

**Primary KPIs:** `observe_ms` sum + share of `step_ms`; wall / `step_ms` sum.  
**Secondary:** steps, `grounder_ms`, `GOAL_REACHED` + human-sane add-to-cart.

**Pass line (suggested):** median over 3 pairs — U2 `observe_ms` ≤ ADB × 0.70 (**≥30% drop**), success rate ≥ ADB. Wall drop is bonus (VLM/act noise).

**Do not:** use MCP wall as primary; change goals mid-A/B; treat a different path (e.g. burger) as this baseline.

### Results table (CLI `scripts/ab-observe-backend.sh`, 2026-11-18, serial `10.10.51.111:44543`)

Raw artifacts: `runs/ab-observe/20261118-141843/`. Model `gui-plus-2026-02-26`. Backends pure (no `u2_fallback_adb`).

| Pair | Arm | run_id | wall_s | observe_ms | obs% | step_ms | status | outcome notes |
|------|-----|--------|--------|------------|------|---------|--------|---------------|
| 1 | adb | 20261118-141845-46e2ee | 169 | 79389 | 76.4 | 103896 | STUCK | A only; a11y `labels=[]`; unchanged×3 |
| 1 | u2 | 20261118-142136-8de03a | 118 | 53982 | 40.1 | 134625 | BUDGET_EXCEEDED | A OK（潮巷粿条+月售）; B max_steps 未进菜单「加入购物车」 |
| 2 | u2 | 20261118-142336-5fcf14 | 127 | 52712 | 32.6 | 161840 | BUDGET_EXCEEDED | A OK; B max_steps 同店列表卡住 |
| 2 | adb | 20261118-142546-0ffe82 | 159 | 70849 | 70.6 | 100311 | STUCK | A only; `labels=[]` |
| 3 | adb | 20261118-142827-0e062d | 151 | 67425 | 71.5 | 94287 | STUCK | A only; `labels=[]` |
| 3 | u2 | 20261118-143100-bdfdc8 | 86 | 25279 | 30.3 | 83555 | BUDGET_EXCEEDED | A max_steps（通知抽屉干扰）; 未加购 |

**Median observe_ms (adb / u2 / Δ%):** 70849 / 52712 / **−25.6%** (plan-total; below ≥30% gate)  
**obs% median:** adb ~71.5% → u2 ~32.6%  
**Per-observe approx:** adb ~11–13 s/obs vs u2 ~2.5–3.4 s/obs (ADB early STUCK → fewer steps; U2 ran longer paths)  
**Full-plan success:** adb 0/3, u2 0/3 (tight checks). Stage A cleared: adb 0/3, u2 2/3.

**Verdict:** On this phone, U2 **does** cut observe share and per-capture latency, and progressed further than ADB (empty-tree STUCK), but **plan-total observe_ms median drop 25.6% misses the ≥30% gate**, and neither arm finished add-to-cart under tight checks. **Do not flip default to U2 yet** for “same-path wall”; keep opt-in (`MAU_OBSERVE_BACKEND=u2`) until a run set clears stage C on both arms with ≥30% observe drop.
