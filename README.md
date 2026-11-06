# mano-android-use (mau)

**English** · [中文](README.zh-CN.md)

Android **MCP Agent tools (A′)** on top of pinned [`mano@v0.1.2`](https://github.com/jimmywang2020/mano.git).

This is a **Consumer / MCP facade** over mano Core — **not** a fork of Core. Use an **independent** project environment (do not activate `mano/`’s `.venv`).

| Layer | Role |
|-------|------|
| **Host** (Cursor / Codex) | Orchestrates with compact UI trees — does **not** need every screenshot |
| **Grounder** | VLM proposes the next UI action (`gui-plus*`, `glm-4.6v-flash*`) |
| **L0** | mano ADB observe / act / journal — **no Pack required** |
| **Safety** | Blocks payment / submit heuristics before ADB |

**In scope:** local/USB/wireless Android (emulator or phone), stdio MCP, bounded `android_run` / staged `run-plan`.  
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

Wireless debug **ports change**; refresh `MANO_DEVICE_SERIAL` (and MCP env) after reconnect.

## CLI

```bash
uv run mau propose "..."                           # MAU_GROUNDER_MODEL (gui-plus by default)
uv run mau propose "..." --model glm-4.6v-flash
uv run mau run "Open Settings" --max-steps 8
uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json
```

| Command | Purpose |
|---------|---------|
| `mau doctor` / `ready` | Device health + tips |
| `mau observe [--detail tree\|screenshot\|both]` | Compact tree + summary (default: no host screenshot) |
| `mau find QUERY` | Tree search (no VLM) |
| `mau tap X Y` / `type` / `press` / `launch` | Act |
| `mau propose "instruction"` | One-shot grounder |
| `mau run "goal" [--package ...] [--success-*]` | Bounded loop + optional `success_check` |
| `mau run-plan <plan.json>` | Staged A/B/C plan |

## MCP (Cursor / Codex) — stdio

Prefer the MuMu wrapper (auto-detect serial):

```json
{
  "mcpServers": {
    "mano-android-use": {
      "command": "/ABS/PATH/TO/mano-android-use/scripts/mau-mcp-with-mumu.sh",
      "args": [],
      "env": {
        "MAU_GROUNDER_MODEL": "gui-plus-2026-02-26",
        "MAU_RUNS_DIR": "/ABS/PATH/TO/mano-android-use/runs",
        "MCP_REV": "open-source"
      }
    }
  }
}
```

Templates: [`examples/mcp.cursor.json`](examples/mcp.cursor.json), [`examples/mcp.codex.toml.example`](examples/mcp.codex.toml.example).

**Cursor:** Customize → MCPs → add user-level server (avoid a duplicate project `.cursor/mcp.json`). Keys stay in project `.env`.

**Tools:** `doctor`, `ready`, `observe`, `find`, `launch_app`, `tap`, `swipe`, `type_text`, `press_button`, `propose_action`, `journal_tail`, `android_run`, `android_run_plan`.

Agent hosts should follow [`docs/agent-playbook.md`](docs/agent-playbook.md). Cursor rule: [`.cursor/rules/mau-android-agent.mdc`](.cursor/rules/mau-android-agent.mdc).

## Grounder models

| Model | Notes |
|-------|--------|
| `gui-plus-2026-02-26` | Recommended default (DashScope) |
| `gui-plus` | Alias family on DashScope |
| `glm-4.6v-flash` | Production-supported (Zhipu) |
| `glm-4.6v-flashx` | Supported id when billing enabled |

## Examples

- Ctrip Beijing homestay (staged plan): [`docs/examples/ctrip-beijing-homestay.md`](docs/examples/ctrip-beijing-homestay.md)
- Plan JSON: [`docs/examples/plans/`](docs/examples/plans/)

## Safety

Payment / order-submit screens → `NEED_HUMAN` or `BLOCKED_BY_POLICY`. The loop stops; do not force taps. Settings rows like「钱包与支付」are **not** treated as payment.

## Layout

```text
scripts/
  mumu-adb.sh              # MuMu ADB serial helper
  mau-mcp-with-mumu.sh     # MCP entry: detect serial then exec mau-mcp
src/mano_android_use/
  session.py grounder.py safety.py tree.py
  run_loop.py run_plan.py success_check.py
  mcp_server.py cli.py
docs/
  agent-playbook.md acceptance.md examples/
```

## Related

- Core library: [jimmywang2020/mano](https://github.com/jimmywang2020/mano)
- Acceptance checklist: [`docs/acceptance.md`](docs/acceptance.md)
