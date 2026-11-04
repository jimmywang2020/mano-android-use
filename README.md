# mano-android-use

Android **MCP Agent tools (A′)** on top of pinned [`mano@v0.1.2`](https://github.com/jimmywang2020/mano.git).

This is a **Consumer / MCP facade** over mano Core — **not** a fork of Core. Use an
**independent** project environment (do not activate `mano/`'s `.venv`).

- **Host** (Cursor / Codex): orchestrates with compact UI trees — does **not** need every screenshot.
- **Grounder** (production-supported): `gui-plus` / `gui-plus-2026-02-26` and `glm-4.6v-flash` (+ `glm-4.6v-flashx`).
- **L0**: mano ADB observe / act / journal — **no Pack required**.
- **Safety**: blocks payment/submit heuristics before ADB.

WeChat entry, Pack acceleration, and cloud devices are **out of v1 scope**.

## Setup (independent env — prefer `uv`)

Python **3.10+** (3.11 recommended). Machine needs `adb` and (for MuMu) a running emulator.

```bash
cd /Users/wangjinxiang/Desktop/Projects/mano-android-use
uv sync --extra dev
cp .env.example .env   # fill BOTH DASHSCOPE_API_KEY and ZHIPU_API_KEY; never commit; no MuMu serial
```

CLI auto-loads `.env`. Switch models without editing keys:

```bash
uv run mau propose "..."                           # uses MAU_GROUNDER_MODEL (gui-plus by default)
uv run mau propose "..." --model glm-4.6v-flash    # uses ZHIPU_API_KEY automatically
uv run mau run "打开设置" --max-steps 8            # B-path: bounded android_run loop
```

Fallback without uv:

```bash
python3.11 -m venv .venv && . .venv/bin/activate
python -m pip install -e '.[dev]'
```

### Device serial (MuMu — do not hardcode ports)

Same helper as mano Core:

```bash
# Start MuMu to the Android desktop first, then:
eval "$(bash scripts/mumu-adb.sh)"
# → exports MANO_DEVICE_SERIAL=127.0.0.1:<detected-port>
uv run mau doctor
uv run mau observe
```

USB device: `export MANO_DEVICE_SERIAL=<serial from adb devices>` yourself.

## CLI

| Command | Purpose |
|---------|---------|
| `uv run mau doctor` / `ready` | Device health |
| `uv run mau observe [--detail tree\|screenshot\|both]` | Default: compact tree + summary |
| `uv run mau find QUERY` | Tree search (no VLM) |
| `uv run mau tap X Y` / `type` / `press` | Act |
| `uv run mau launch PACKAGE` | Cold start |
| `uv run mau propose "instruction" [--model ...]` | Grounder |
| `uv run mau run "goal" [--max-steps N] [--model ...] [--package ...]` | B-path: bounded `android_run` |

## MCP (Cursor + Codex)

Prefer the MuMu wrapper (auto-detect serial, no `16384` in config).

### Cursor (Customize → MCPs，不是旧版 Settings 独占入口)

1. 用 Cursor **打开本仓库** `mano-android-use` 作为工作区。
2. 打开 **Customize**（或 Command Palette 搜 `MCP`）→ 筛选项选 **MCPs**。
3. 点 **New MCP Server** / **Add a Custom MCP Server**。
4. 把 [`examples/mcp.cursor.json`](examples/mcp.cursor.json) 写入 **用户级** MCP（Customize → New MCP Server）。本仓**不**提交项目级 `.cursor/mcp.json`，避免与 User 配置重复。
5. 回到 Customize → MCPs，确认 **Connected** 只有一份 `mano-android-use`（绿点 / tools enabled）。
6. Key 读项目根目录 `.env`；MCP `env` 不必再塞 Key。

Codex: [`examples/mcp.codex.toml.example`](examples/mcp.codex.toml.example)。

Tools: `doctor`, `ready`, `observe`, `find`, `launch_app`, `tap`, `swipe`, `type_text`, `press_button`, `propose_action`, `journal_tail`, `android_run`.

## Grounder models

| Model | Role |
|-------|------|
| `gui-plus-2026-02-26` | Recommended default (mano-validated) |
| `gui-plus` | Alias family on DashScope |
| `glm-4.6v-flash` | **Production-supported** (Zhipu); set `MAU_GROUNDER_BASE_URL` |
| `glm-4.6v-flashx` | Supported id; wire when you enable billing |

## Acceptance

See [`docs/acceptance.md`](docs/acceptance.md). **Phase 5 requires you to run one short task in Cursor and one in Codex.**

## Layout

```text
scripts/
  mumu-adb.sh              # from mano Core — auto-detect MuMu ADB
  mau-mcp-with-mumu.sh     # MCP entry: detect then exec mau-mcp
src/mano_android_use/
  session.py grounder.py safety.py tree.py run_loop.py mcp_server.py cli.py
```
