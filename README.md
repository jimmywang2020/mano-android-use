# mano-android-use (mau)

**English** · [中文](README.zh-CN.md)

Android **MCP Agent tools (A′)** on top of pinned [`mano@v0.1.4`](https://github.com/jimmywang2020/mano.git).

This is a **Consumer / MCP facade** over mano Core — **not** a fork of Core. Use an
**independent** project environment (do not activate `mano/`’s `.venv`).

| Layer | Role |
|-------|------|
| **Host** (Cursor / Codex) | Picks **goal/plan**; merges `task_patch` into TaskState; corrects from compact trees — does **not** need every screenshot |
| **mau loop** | `android_run` / `android_run_plan` bounded orchestration |
| **Grounder** | VLM sees on-disk screenshots only; proposes next action (`gui-plus*`, `glm-4.6v-flash*`) |
| **L0** | Sole executor: mano ADB observe / act / journal — **no Pack required** |
| **Safety** | Blocks payment / submit heuristics before ADB |

**In scope:** local/USB/wireless Android (emulator or phone), stdio MCP, bounded
`android_run` / staged `run-plan`, Host resume via `task_patch` + `progress_json`,
recipe gates (`labels_all` / `forbid_labels`), optional U2 observe backend.  
**Out of v1:** WeChat ingress, Pack acceleration, cloud device farms, iOS.

License: [MIT](LICENSE).

---

## Requirements

- Python **3.10+** (3.11 recommended)
- [`uv`](https://github.com/astral-sh/uv) recommended (or venv + pip)
- `adb` on `PATH`
- A device: MuMu / other emulator, or USB / wireless phone
- API keys for the grounder you use (DashScope and/or Zhipu) — see [`.env.example`](.env.example)

## Setup

```bash
git clone https://github.com/jimmywang2020/mano-android-use.git
cd mano-android-use
uv sync --extra dev
cp .env.example .env   # fill keys; never commit .env
```

Optional faster observe (does **not** change the default):

```bash
uv sync --extra u2 --extra dev
# then: export MAU_OBSERVE_BACKEND=u2
```

Fallback without uv:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -e '.[dev]'
```

### Device serial

MuMu (do **not** hardcode ports):

```bash
# Start MuMu to the Android desktop first, then:
eval "$(bash scripts/mumu-adb.sh)"
# → exports MANO_DEVICE_SERIAL=127.0.0.1:<detected-port>
uv run mau doctor
uv run mau ready
```

USB / wireless phone:

```bash
adb devices
export MANO_DEVICE_SERIAL=<serial from adb devices>   # e.g. 192.168.x.x:port
```

Wireless debug **ports change**; refresh `MANO_DEVICE_SERIAL` (and MCP env) after
reconnect. Prefer MCP command `scripts/mau-mcp-with-mumu.sh` so serial is
re-resolved on each MCP start.

---

## Host resume / TaskState

Every `android_run` / `android_run_plan` return includes a stable **`task_patch`**
(`schema: mau.task_patch.v1`) plus aliases `resume` / `continue_hint`.

| Field | Role |
|-------|------|
| `progress` / `plan_progress` | OR-merge facts (`fare_seen`, `goal_matched`, …) |
| `resume` | ResumeSpec — `next_actor=done` or `host` + `do` / `dont` |
| `screen_digest` / `evidence_refs` | Filtered labels + screenshot/xml paths |

**Host resume = fill the form** (do not rewrite the goal from chat prose):

1. Merge `task_patch` into local TaskState (OR-merge `progress`; replace `resume` /
   `screen_digest`). Helper: `merge_task_state` in `run_loop` (mau does **not**
   persist Host disk).
2. If `next_actor=host`, call `android_run` with `resume.do`: same goal,
   **omit `package=`**, `cold_start=false`, keep `tree_hints` / `success_check`.
3. Pass **`progress_json`** = `JSON.stringify(TaskState.progress)` so mau OR-seeds
   facts across short MCP calls.
4. Honor `dont[]`: no `HOME`, no `force_stop` / cold `launch_app`, no
   `rewrite_goal_from_scratch`, no `propose_action` main loop.

Shape example: [`docs/examples/task-state.example.json`](docs/examples/task-state.example.json).  
Full playbook: [`docs/agent-playbook.md`](docs/agent-playbook.md).

Within one `android_run_plan`, stage progress is OR-merged automatically into
`plan_progress`. Across separate MCP `android_run` calls, Host must carry
`progress_json`.

---

## Recipe gates (success predicates)

**Memory resumes work; gates define success.** Loose `labels_any` (especially
dest-name alone on a search sheet) causes false `GOAL_REACHED`.

| Rule | Production |
|------|------------|
| Terminal stage | Prefer **`labels_all`** (e.g. DiDi fare: `未拼成` + `一口价`) |
| Dest stage | Fare-sheet signals (`选路线` / `一口价` / …), **not** dest-name OR alone |
| Absent UI | **`forbid_labels`** / MCP `success_forbid_labels` / CLI `--success-forbid-label` (e.g. `请输入终点`) |
| Fixtures | Do **not** treat `role: fixture` plans as production truth |

DiDi recipe: [`docs/recipes/didi.md`](docs/recipes/didi.md).  
Production plan: [`docs/examples/plans/didi-airport-carpool-vs-special.json`](docs/examples/plans/didi-airport-carpool-vs-special.json).  
Fixture only: [`docs/examples/plans/ab-didi-xiangmihu-fare.json`](docs/examples/plans/ab-didi-xiangmihu-fare.json).

---

## Observe backend

| Backend | How |
|---------|-----|
| **ADB** (default) | Unset or `MAU_OBSERVE_BACKEND=adb` |
| **U2** (opt-in) | `uv sync --extra u2` then `MAU_OBSERVE_BACKEND=u2`; on failure same step falls back to ADB (`u2_fallback_adb`) |

Latency notes / A/B method: [`docs/eval-latency.md`](docs/eval-latency.md). Default remains ADB until a same-path wall gate is met.

---

## CLI

```bash
uv run mau propose "..."                           # MAU_GROUNDER_MODEL (gui-plus by default)
uv run mau propose "..." --model glm-4.6v-flash
uv run mau run "Open Settings" --max-steps 8
uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json
uv run mau run-plan docs/examples/plans/didi-airport-carpool-vs-special.json
```

| Command | Purpose |
|---------|---------|
| **Goal / orchestration** | |
| `mau run "goal"` | **Primary:** bounded loop; tree-first + unchanged-screen VLM skip |
| `mau run-plan <plan.json>` | **Long tasks:** staged A/B/C plan (cross-stage `plan_progress` OR-merge) |
| `mau doctor` / `ready` | Device health + tips (`screen`, `text_backend`, `observe_backend`) |
| `mau trace [runs/<id>]` | Step timing/token table (`via` + `by_via`) from `trace.json` / journal (`--json`) |
| **`mau run` flags** | |
| `--package` / `--cold-start` | Warm ensure by default; cold only for true relaunch |
| `--success-package` / `--success-label` / `--success-label-all` | External success_check |
| `--success-forbid-label` | `forbid_labels` / require_absent (repeatable) |
| `--tree-hint` | Tree-first find before VLM (repeatable) |
| `--stuck-same-summary N` | Unchanged-screen threshold (default 3; `0`=off; env `MAU_STUCK_SAME_SUMMARY`) |
| `--wall-budget-ms` | Soft wall budget (MCP-like resume demos); `0`=off |
| `--progress-json` | Host TaskState progress seed, e.g. `'{"fare_seen":true}'` |
| **L0 correction** | |
| `mau observe` / `find` / `tap` / `type` / `press` / `launch` | Install dialogs, one-off fixes |
| **Debug** | |
| `mau propose "instruction"` | One-shot grounder (default: no execute; not the main loop) |

---

## MCP (Cursor / Codex) — stdio

Prefer the device wrapper (auto-resolves serial each MCP start):

```json
{
  "mcpServers": {
    "mano-android-use": {
      "command": "/ABS/PATH/TO/mano-android-use/scripts/mau-mcp-with-mumu.sh",
      "args": [],
      "env": {
        "MAU_GROUNDER_MODEL": "gui-plus-2026-02-26",
        "MAU_RUNS_DIR": "/ABS/PATH/TO/mano-android-use/runs",
        "MCP_REV": "open-source",
        "MAU_OBSERVE_BACKEND": "u2"
      }
    }
  }
}
```

`MAU_OBSERVE_BACKEND` is optional (omit or `"adb"` for default).  
`mau-mcp-with-mumu.sh` calls [`scripts/resolve-adb-serial.sh`](scripts/resolve-adb-serial.sh):
keeps `MANO_DEVICE_SERIAL` only if still `device`, otherwise picks a live wireless
`ip:port` / USB / MuMu serial. **Do not pin a wireless port in MCP `env`** — ports
change and would go stale; pair/connect with `adb` first, then start/reconnect MCP.

Templates: [`examples/mcp.cursor.json`](examples/mcp.cursor.json),
[`examples/mcp.codex.toml.example`](examples/mcp.codex.toml.example).

**Cursor:** Customize → MCPs → add user-level server (avoid a duplicate project
`.cursor/mcp.json`). Keys stay in project `.env`. After pulling new tool params
(`progress_json`, `success_forbid_labels`), **reload the MCP** so the live server
picks them up (Cursor’s tool-schema cache may lag; calls can still work).

**Tool groups:**

| Group | Tools |
|-------|--------|
| Goal / orchestration | `android_run`, `android_run_plan`, `ready`, `doctor`, `launch_app`, `journal_tail` |
| L0 correction | `observe`, `find`, `tap`, `swipe`, `type_text`, `press_button` |
| Debug | `propose_action` (`execute=true` deprecated; needs `MAU_ALLOW_PROPOSE_EXECUTE=1`) |

**`android_run` (MCP)** defaults: `max_steps=10`, ~90s soft wall budget. Important
args beyond `goal`: `package`, `cold_start`, `success_package`,
`success_labels_any` / `success_labels_all`, **`success_forbid_labels`**,
`tree_hints`, **`progress_json`**, `stuck_same_summary`.

On `TIME_BUDGET` / `BUDGET_EXCEEDED` / `STUCK`: read **`task_patch`** / `resume`,
re-call short `android_run` (omit package, `cold_start=false`, pass
`progress_json`) — do **not** switch the main loop to L0. Long jobs: CLI
`mau run` / `mau run-plan`, or multiple short MCP stages / `android_run_plan`.

Always relay `cost_report.narrative` (+ `dominant_phase`) to the user after each run.

Agent hosts should follow [`docs/agent-playbook.md`](docs/agent-playbook.md).  
Cursor rule: [`.cursor/rules/mau-android-agent.mdc`](.cursor/rules/mau-android-agent.mdc).  
Golden tasks: [`docs/eval-golden.md`](docs/eval-golden.md).

---

## Grounder models

| Model | Notes |
|-------|--------|
| `gui-plus-2026-02-26` | Recommended default (DashScope) |
| `gui-plus` | Alias family on DashScope |
| `glm-4.6v-flash` | Production-supported (Zhipu) |
| `glm-4.6v-flashx` | Supported id when billing enabled |

---

## Examples

- Ctrip Beijing homestay (staged plan): [`docs/examples/ctrip-beijing-homestay.md`](docs/examples/ctrip-beijing-homestay.md)
- Plan JSON: [`docs/examples/plans/`](docs/examples/plans/)
- DiDi fare recipe + gates: [`docs/recipes/didi.md`](docs/recipes/didi.md)
- Host TaskState shape: [`docs/examples/task-state.example.json`](docs/examples/task-state.example.json)

## Safety

Payment / order-submit screens → `NEED_HUMAN` or `BLOCKED_BY_POLICY`. The loop
stops; do not force taps. Settings rows like「钱包与支付」are **not** treated as
payment.

## Layout

```text
scripts/
  mumu-adb.sh              # MuMu ADB serial helper
  mau-mcp-with-mumu.sh     # MCP entry: detect serial then exec mau-mcp
  resolve-adb-serial.sh    # Keep live serial / re-pick wireless
src/mano_android_use/
  session.py grounder.py safety.py tree.py
  run_loop.py run_plan.py success_check.py
  mcp_server.py cli.py
docs/
  agent-playbook.md acceptance.md plan-next.md
  recipes/ examples/ eval-*.md
```

## Related

- Core library: [jimmywang2020/mano](https://github.com/jimmywang2020/mano) (`v0.1.4`)
- Acceptance checklist: [`docs/acceptance.md`](docs/acceptance.md)
- Active / deferred roadmap: [`docs/plan-next.md`](docs/plan-next.md)
