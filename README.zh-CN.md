# mano-android-use (mau)

[English](README.md) · **中文**

基于已 pin 的 [`mano@v0.1.2`](https://github.com/jimmywang2020/mano.git) 的 Android **MCP Agent 工具（A′）**。

本仓是 mano Core 之上的 **Consumer / MCP 门面**，**不是** Core 的 fork。请使用**独立**项目环境（不要激活 `mano/` 的 `.venv`）。

| 层 | 作用 |
|----|------|
| **Host**（Cursor / Codex） | 用精简控件树编排；**不需要**每步看截图 |
| **Grounder** | VLM 提出下一步 UI 动作（`gui-plus*`、`glm-4.6v-flash*`） |
| **L0** | mano ADB 观察 / 执行 / journal — **不需要 Pack** |
| **Safety** | 支付 / 提交类启发式在打到 ADB 前拦截 |

**范围内：** 本机 USB / 无线安卓（模拟器或真机）、stdio MCP、有界 `android_run` / 分阶段 `run-plan`。  
**v1 不做：** 微信入口、Pack 加速、云真机农场、iOS。

许可证：[MIT](LICENSE)。

---

## 环境要求

- Python **3.10+**（推荐 3.11）
- 推荐 [`uv`](https://github.com/astral-sh/uv)（也可用 venv + pip）
- `PATH` 中有 `adb`
- 设备：MuMu / 其他模拟器，或 USB / 无线真机
- Grounder 所需 API Key（DashScope 和/或 智谱）— 见 [`.env.example`](.env.example)

## 安装

```bash
git clone https://github.com/jimmywang2020/mano-android-use.git
cd mano-android-use
uv sync --extra dev
cp .env.example .env   # 填入密钥；勿提交 .env
```

不用 uv 时：

```bash
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -e '.[dev]'
```

### 设备串号

MuMu（**不要**写死端口）：

```bash
# 先启动 MuMu 到安卓桌面，再：
eval "$(bash scripts/mumu-adb.sh)"
# → 导出 MANO_DEVICE_SERIAL=127.0.0.1:<探测到的端口>
uv run mau doctor
uv run mau ready
```

USB / 无线真机：

```bash
adb devices
export MANO_DEVICE_SERIAL=<adb devices 中的串号>   # 如 192.168.x.x:port
```

无线调试**端口会变**；重连后请更新 `MANO_DEVICE_SERIAL`（及 MCP 环境变量）。

## CLI

```bash
uv run mau propose "..."                           # 默认 MAU_GROUNDER_MODEL（gui-plus）
uv run mau propose "..." --model glm-4.6v-flash
uv run mau run "打开设置" --max-steps 8
uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json
```

| 命令 | 用途 |
|------|------|
| `mau doctor` / `ready` | 设备健康检查 + tips |
| `mau observe [--detail tree\|screenshot\|both]` | 精简树 + 摘要（默认不给 Host 截图） |
| `mau find QUERY` | 树内搜索（无 VLM） |
| `mau tap X Y` / `type` / `press` / `launch` | 执行动作 |
| `mau propose "instruction"` | 单次 Grounder |
| `mau run "goal" [--package ...] [--success-*]` | 有界循环 + 可选 `success_check` |
| `mau run-plan <plan.json>` | 分阶段 A/B/C plan |

## MCP（Cursor / Codex）— stdio

推荐 MuMu 包装脚本（自动探测串号）：

```json
{
  "mcpServers": {
    "mano-android-use": {
      "command": "/绝对路径/mano-android-use/scripts/mau-mcp-with-mumu.sh",
      "args": [],
      "env": {
        "MAU_GROUNDER_MODEL": "gui-plus-2026-02-26",
        "MAU_RUNS_DIR": "/绝对路径/mano-android-use/runs",
        "MCP_REV": "open-source"
      }
    }
  }
}
```

模板：[`examples/mcp.cursor.json`](examples/mcp.cursor.json)、[`examples/mcp.codex.toml.example`](examples/mcp.codex.toml.example)。

**Cursor：** Customize → MCPs → 添加**用户级**服务器（避免再提交一份项目级 `.cursor/mcp.json`）。密钥放在项目 `.env`。

**工具：** `doctor`、`ready`、`observe`、`find`、`launch_app`、`tap`、`swipe`、`type_text`、`press_button`、`propose_action`、`journal_tail`、`android_run`、`android_run_plan`。

Agent 请遵循 [`docs/agent-playbook.md`](docs/agent-playbook.md)。Cursor 规则：[`.cursor/rules/mau-android-agent.mdc`](.cursor/rules/mau-android-agent.mdc)。

## Grounder 模型

| 模型 | 说明 |
|------|------|
| `gui-plus-2026-02-26` | 推荐默认（DashScope） |
| `gui-plus` | DashScope 别名族 |
| `glm-4.6v-flash` | 生产支持（智谱） |
| `glm-4.6v-flashx` | 开通计费后可用 |

## 示例

- 携程北京民宿（分阶段 plan）：[`docs/examples/ctrip-beijing-homestay.md`](docs/examples/ctrip-beijing-homestay.md)
- Plan JSON：[`docs/examples/plans/`](docs/examples/plans/)

## 安全

进入支付 / 提交订单页 → `NEED_HUMAN` 或 `BLOCKED_BY_POLICY`，循环停止，不要强行点击。设置里的「钱包与支付」等**不算**支付页。

## 目录结构

```text
scripts/
  mumu-adb.sh              # MuMu ADB 串号助手
  mau-mcp-with-mumu.sh     # MCP 入口：探测串号后执行 mau-mcp
src/mano_android_use/
  session.py grounder.py safety.py tree.py
  run_loop.py run_plan.py success_check.py
  mcp_server.py cli.py
docs/
  agent-playbook.md acceptance.md examples/
```

## 相关链接

- Core 库：[jimmywang2020/mano](https://github.com/jimmywang2020/mano)
- 验收清单：[`docs/acceptance.md`](docs/acceptance.md)
