#!/usr/bin/env bash
# Same-path A/B: MAU_OBSERVE_BACKEND=adb vs u2 on fixed guotiao plan.
# Usage: bash scripts/ab-observe-backend.sh [pairs=3]
# Writes JSON arms under runs/ab-observe/<stamp>/ and prints a markdown table.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PAIRS="${1:-3}"
PLAN="${AB_PLAN:-docs/examples/plans/ab-meituan-guotiao-20.json}"
MODEL="${MAU_GROUNDER_MODEL:-gui-plus-2026-02-26}"
PKG="${AB_PACKAGE:-com.sankuai.meituan}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="runs/ab-observe/${STAMP}"
mkdir -p "$OUT_DIR" runs/ab-observe

eval "$(bash scripts/resolve-adb-serial.sh)"
echo "serial=${MANO_DEVICE_SERIAL} plan=${PLAN} model=${MODEL} pairs=${PAIRS}" | tee "$OUT_DIR/meta.txt"

reset_meituan() {
  adb -s "$MANO_DEVICE_SERIAL" shell am force-stop "$PKG" >/dev/null 2>&1 || true
  sleep 2
}

# Extract metrics from mau run-plan JSON stdout file.
summarize_arm() {
  local json_path="$1"
  python3 - "$json_path" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
raw = p.read_text(encoding="utf-8")
# mau may print non-JSON lines; take last {...} object
doc = None
for i, ch in enumerate(raw):
    if ch == "{":
        try:
            doc = json.loads(raw[i:])
            break
        except json.JSONDecodeError:
            continue
if doc is None:
    print("PARSE_FAIL||||")
    sys.exit(0)
cr = doc.get("cost_report") or {}
bp = (cr.get("by_phase") or {}).get("observe") or {}
obs = int(bp.get("ms") or 0)
total = int(cr.get("total_ms") or 0)
pct = bp.get("pct")
if pct is None and total:
    pct = round(100.0 * obs / total, 1)
status = doc.get("status") or ""
# by_backend across stages
backends = {}
for st in (cr.get("stages") or []):
    ob = ((st.get("by_phase") or {}).get("observe") or {}).get("by_backend") or {}
    for k, v in ob.items():
        backends[k] = backends.get(k, 0) + int(v or 0)
# also top-level observe by_backend if present
for k, v in (bp.get("by_backend") or {}).items():
    backends[k] = backends.get(k, 0) + int(v or 0)
run_ids = []
for st in doc.get("stages") or []:
    r = st.get("result") if isinstance(st.get("result"), dict) else {}
    rid = r.get("run_id") or ""
    if rid:
        run_ids.append(str(rid))
rid = "+".join(run_ids) if run_ids else (doc.get("run_id") or p.stem)
fallback = "u2_fallback_adb" in backends
print(f"{rid}|{status}|{obs}|{pct}|{total}|{json.dumps(backends, ensure_ascii=False)}|{int(fallback)}")
PY
}

RESULTS_TSV="$OUT_DIR/results.tsv"
echo -e "pair\tarm\trun_id\tstatus\tobs_ms\tobs_pct\tstep_ms\tbackends\tfallback\twall_s\tjson" > "$RESULTS_TSV"

for ((pair=1; pair<=PAIRS; pair++)); do
  eval "$(bash scripts/resolve-adb-serial.sh)"
  if (( pair % 2 == 1 )); then
    FIRST=adb
    SECOND=u2
  else
    FIRST=u2
    SECOND=adb
  fi
  for arm in "$FIRST" "$SECOND"; do
    reset_meituan
    json_out="$OUT_DIR/pair${pair}_${arm}.json"
    echo "=== pair=${pair} arm=${arm} start $(date -Iseconds) ===" | tee -a "$OUT_DIR/log.txt"
    t0=$(date +%s)
    set +e
    MAU_OBSERVE_BACKEND="$arm" \
      uv run mau run-plan "$PLAN" --model "$MODEL" >"$json_out" 2>"$OUT_DIR/pair${pair}_${arm}.stderr"
    rc=$?
    set -e
    t1=$(date +%s)
    wall=$((t1 - t0))
    metrics="$(summarize_arm "$json_out")"
    IFS='|' read -r rid status obs pct total backends fallback <<<"$metrics"
    if [[ "$arm" == "u2" && "$fallback" == "1" ]]; then
      echo "VOID pair=${pair} arm=u2: u2_fallback_adb present — rerunning once" | tee -a "$OUT_DIR/log.txt"
      reset_meituan
      t0=$(date +%s)
      set +e
      MAU_OBSERVE_BACKEND=u2 \
        uv run mau run-plan "$PLAN" --model "$MODEL" >"$json_out" 2>"$OUT_DIR/pair${pair}_${arm}.stderr"
      rc=$?
      set -e
      t1=$(date +%s)
      wall=$((t1 - t0))
      metrics="$(summarize_arm "$json_out")"
      IFS='|' read -r rid status obs pct total backends fallback <<<"$metrics"
    fi
    echo -e "${pair}\t${arm}\t${rid}\t${status}\t${obs}\t${pct}\t${total}\t${backends}\t${fallback}\t${wall}\t${json_out}" >> "$RESULTS_TSV"
    echo "pair=${pair} arm=${arm} rc=${rc} wall_s=${wall} status=${status} obs_ms=${obs} obs%=${pct} step_ms=${total} backends=${backends}" | tee -a "$OUT_DIR/log.txt"
  done
done

echo
echo "### Results (${OUT_DIR})"
echo "| Pair | Arm | run_id | wall_s | observe_ms | obs% | step_ms | status | backends |"
echo "|------|-----|--------|--------|------------|------|---------|--------|----------|"
tail -n +2 "$RESULTS_TSV" | while IFS=$'\t' read -r pair arm rid status obs pct total backends fallback wall json; do
  echo "| ${pair} | ${arm} | ${rid} | ${wall} | ${obs} | ${pct} | ${total} | ${status} | ${backends} |"
done

python3 - "$RESULTS_TSV" <<'PY'
import csv, statistics, sys
from pathlib import Path
rows = list(csv.DictReader(Path(sys.argv[1]).open(), delimiter="\t"))
adb = [int(r["obs_ms"]) for r in rows if r["arm"] == "adb" and r["obs_ms"].isdigit()]
u2 = [int(r["obs_ms"]) for r in rows if r["arm"] == "u2" and r["obs_ms"].isdigit()]
def med(xs):
    return statistics.median(xs) if xs else None
ma, mu = med(adb), med(u2)
print()
if ma is not None and mu is not None and ma > 0:
    drop = 100.0 * (1.0 - mu / ma)
    print(f"Median observe_ms adb={ma} u2={mu} drop={drop:.1f}% (pass if drop≥30)")
else:
    print(f"Median observe_ms adb={ma} u2={mu}")
def ok(r):
    return str(r.get("status") or "").upper() in {"GOAL_REACHED", "OK", "SUCCESS"}
adb_n = sum(1 for r in rows if r["arm"] == "adb")
u2_n = sum(1 for r in rows if r["arm"] == "u2")
adb_ok = sum(1 for r in rows if r["arm"] == "adb" and ok(r))
u2_ok = sum(1 for r in rows if r["arm"] == "u2" and ok(r))
print(f"Full-plan success (GOAL_REACHED/OK): adb={adb_ok}/{adb_n} u2={u2_ok}/{u2_n}")
print(f"Results TSV: {sys.argv[1]}")
PY
