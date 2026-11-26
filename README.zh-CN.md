# mano-android-use (mau)

[English](README.md) · **中文**

基于已 pin 的 [`mano@v0.1.4`](https://github.com/jimmywang2020/mano.git) 的 Android **MCP Agent 工具（A′）**。

本仓是 mano Core 之上的 **Consumer / MCP 门面**，**不是** Core 的 fork。请使用**独立**项目环境（不要激活 `mano/` 的 `.venv`）。

| 层 | 作用 |
|----|------|
| **Host**（Cursor / Codex） | **选题**（goal / plan）；合并 `task_patch` 到 TaskState；用精简树纠偏；**不需要**每步看截图 |
| **mau 编排** | `android_run` / `android_run_plan` 有界循环 |
| **Grounder** | VLM 只看盘上截图，提出下一步动作（`gui-plus*`、`glm-4.6v-flash*`） |
| **L0** | 唯一执行面：mano ADB 观察 / 执行 / journal — **不需要 Pack** |
| **Safety** | 支付 / 提交类启发式在打到 ADB 前拦截 |

**范围内：** 本机 USB / 无线安卓（模拟器或真机）、stdio MCP、有界 `android_run` / 分阶段 `run-plan`、Host 经 `task_patch` + `progress_json` 续跑、recipe 门禁（`labels_all` / `forbid_labels`）、可选 U2 observe。  
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

可选更快 observe（**不**改变默认）：

```bash
uv sync --extra u2 --extra dev
# 然后: export MAU_OBSERVE_BACKEND=u2
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

无线调试**端口会变**；重连后请更新 `MANO_DEVICE_SERIAL`（及 MCP 环境变量）。推荐 MCP 使用
`scripts/mau-mcp-with-mumu.sh`，每次启动自动解析串号。

---

## Host 续跑 / TaskState

每次 `android_run` / `android_run_plan` 回包都带稳定 **`task_patch`**
（`schema: mau.task_patch.v1`）以及别名 `resume` / `continue_hint`。

| 字段 | 作用 |
|------|------|
| `progress` / `plan_progress` | OR-merge 事实 — 优先 `completed_slots` / `world` / `policy`（见 playbook **Progress contract** + **Guard**）；旧字段 `fare_seen` / `goal_matched` 仍可用。`world.sku_keys` 命中时 Guard 会对重复选规格/加购 NO_OP |
| `resume` | ResumeSpec — `next_actor=done` 或 `host` + `do` / `dont` |
| `screen_digest` / `evidence_refs` | 过滤后标签 + 截图/xml 路径 |

**Host 续跑 = 填表**，不要用聊天散文重写目标：

1. 合并 `task_patch` 到本地 TaskState（OR-merge `progress`；替换 `resume` /
   `screen_digest`）。辅助函数：`run_loop.merge_task_state`（mau **不**替 Host 落盘）。
2. 若 `next_actor=host`，按 `resume.do` 调 `android_run`：同一 goal、**省略
   `package=`**、`cold_start=false`，保留 `tree_hints` / `success_check`。
3. 传 **`progress_json`** = `JSON.stringify(TaskState.progress)`，跨短 MCP 调用 OR-种子。
4. 遵守 `dont[]`：禁止 `HOME`、`force_stop` / 冷启 `launch_app`、从零改写 goal、
   `propose_action` 主循环。

形状示例：[`docs/examples/task-state.example.json`](docs/examples/task-state.example.json)。  
完整 playbook：[`docs/agent-playbook.md`](docs/agent-playbook.md)。

同一次 `android_run_plan` 内 stage progress 会自动 OR-merge 为 `plan_progress`；
跨多次 MCP `android_run` 必须由 Host 携带 `progress_json`。

---

## Recipe 门禁（成功谓词）

**记忆管接着干；门禁管算不算干完。** 松 `labels_any`（尤其搜索页仅靠地名）会导致假
`GOAL_REACHED`。

| 规则 | 生产要求 |
|------|----------|
| 终态 stage | 优先 **`labels_all`**（如滴滴报价：`未拼成` + `一口价`） |
| 设终点 stage | 用报价态信号（`选路线` / `一口价`…），**禁止**仅靠地名 OR |
| 反例禁词 | **`forbid_labels`** / MCP `success_forbid_labels` / CLI `--success-forbid-label`（如 `请输入终点`） |
| 夹具 | **不要**把 `role: fixture` plan 当生产真理 |

滴滴 recipe：[`docs/recipes/didi.md`](docs/recipes/didi.md)。  
美团加购 / DONE 证据：[`docs/recipes/meituan.md`](docs/recipes/meituan.md)。  
Host SlotSpec 薄库：[`docs/examples/slots/`](docs/examples/slots/)（`mano_android_use.host_slots`）。  
反重做 KPI：`mau kpi [runs/<id>]` / `cost_report.kpis`。  
生产 plan：[`docs/examples/plans/didi-airport-carpool-vs-special.json`](docs/examples/plans/didi-airport-carpool-vs-special.json)。  
仅夹具：[`docs/examples/plans/ab-didi-xiangmihu-fare.json`](docs/examples/plans/ab-didi-xiangmihu-fare.json)。

---

## Observe 后端

| 后端 | 用法 |
|------|------|
| **ADB**（默认） | 不设或 `MAU_OBSERVE_BACKEND=adb` |
| **U2**（可选） | `uv sync --extra u2` 后设 `MAU_OBSERVE_BACKEND=u2`；失败则同步回退 ADB（`u2_fallback_adb`） |

延迟说明 / A/B：[`docs/eval-latency.md`](docs/eval-latency.md)。在同路径 wall 门禁达成前默认仍为 ADB。

---

## CLI

```bash
uv run mau propose "..."                           # 默认 MAU_GROUNDER_MODEL（gui-plus）
uv run mau propose "..." --model glm-4.6v-flash
uv run mau run "打开设置" --max-steps 8
uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json
uv run mau run-plan docs/examples/plans/didi-airport-carpool-vs-special.json
```

| 命令 | 用途 |
|------|------|
| **选题 / 编排** | |
| `mau run "goal"` | **主路径**：有界循环；tree-first + 同屏跳过 VLM |
| `mau run-plan <plan.json>` | **长任务**：分阶段 A/B/C（跨 stage `plan_progress` OR-merge） |
| `mau doctor` / `ready` | 设备健康 + tips（`screen`、`text_backend`、`observe_backend`） |
| `mau trace [runs/<id>]` | 逐步耗时/token 表（`via` + `by_via`）+ KPI 块（`--json`） |
| `mau kpi [runs/<id>]` | 反重做 KPI（`guard_noop`、`redo_same_act_class`、`l0_share`…） |
| `mau resume-from-run [runs/<id>]` | MCP 丢包后：从 journal 草稿 TaskState（可选 `--slots`） |
| **`mau run` 常用参数** | |
| `--package` / `--cold-start` | 默认暖启动；仅真冷启时加 `--cold-start` |
| `--success-package` / `--success-label` / `--success-label-all` | 外部 success_check |
| `--success-forbid-label` | `forbid_labels` / require_absent（可重复） |
| `--tree-hint` | VLM 前 tree-first（可重复） |
| `--stuck-same-summary N` | 同屏阈值（默认 3；`0`=关；环境变量 `MAU_STUCK_SAME_SUMMARY`） |
| `--wall-budget-ms` | 软墙钟（模拟 MCP 续跑）；`0`=关 |
| `--progress-json` | Host TaskState 进度种子，如 `'{"fare_seen":true}'` |
| **纠偏（L0）** | |
| `mau observe` / `find` / `tap` / `type` / `press` / `launch` | 装包弹窗、单次纠偏 |
| **调试** | |
| `mau propose "instruction"` | 单次 Grounder（默认不执行；勿当主循环） |

---

## MCP（Cursor / Codex）— stdio

推荐设备包装脚本（**每次 MCP 启动自动解析串号**）：

```json
{
  "mcpServers": {
    "mano-android-use": {
      "command": "/绝对路径/mano-android-use/scripts/mau-mcp-with-mumu.sh",
      "args": [],
      "env": {
        "MAU_GROUNDER_MODEL": "gui-plus-2026-02-26",
        "MAU_RUNS_DIR": "/绝对路径/mano-android-use/runs",
        "MCP_REV": "open-source",
        "MAU_OBSERVE_BACKEND": "u2"
      }
    }
  }
}
```

`MAU_OBSERVE_BACKEND` 可选（省略或 `"adb"` 为默认）。  
`mau-mcp-with-mumu.sh` 会调用 [`scripts/resolve-adb-serial.sh`](scripts/resolve-adb-serial.sh)：
仅当现有 `MANO_DEVICE_SERIAL` 仍是 `device` 时保留，否则从当前 `adb devices` 选取无线
`ip:port` / USB / MuMu。**不要在 MCP `env` 里写死无线端口**；先 `adb pair` /
`adb connect`，再启动或重连 MCP。

模板：[`examples/mcp.cursor.json`](examples/mcp.cursor.json)、
[`examples/mcp.codex.toml.example`](examples/mcp.codex.toml.example)。

**Cursor：** Customize → MCPs → 添加**用户级**服务器（避免再提交一份项目级
`.cursor/mcp.json`）。密钥放在项目 `.env`。拉取含新参数（`progress_json`、
`success_forbid_labels`）的版本后请**重载 MCP**（工具 schema 缓存可能滞后，但调用仍可通）。

**工具分组：**

| 组 | 工具 |
|----|------|
| 选题 / 编排 | `android_run`、`android_run_plan`、`ready`、`doctor`、`launch_app`、`journal_tail` |
| 纠偏 L0 | `observe`、`find`、`tap`、`swipe`、`type_text`、`press_button` |
| 调试 | `propose_action`（`execute=true` 已废弃，需 `MAU_ALLOW_PROPOSE_EXECUTE=1`） |

**`android_run`（MCP）** 默认：`max_steps=10`，约 90s 软墙钟。除 `goal` 外常用：
`package`、`cold_start`、`success_package`、`success_labels_any` /
`success_labels_all`、**`success_forbid_labels`**、`tree_hints`、**`progress_json`**、
`stuck_same_summary`。

遇到 `TIME_BUDGET` / `BUDGET_EXCEEDED` / `STUCK`：读 **`task_patch`** / `resume`，
再短调 `android_run`（省略 package、`cold_start=false`、带 `progress_json`）—
**不要**把主循环改成 L0。长任务用 CLI `mau run` / `mau run-plan`，或多次短 MCP /
`android_run_plan`。

每次跑完务必向用户转述 `cost_report.narrative`（及 `dominant_phase`）。

Agent 请遵循 [`docs/agent-playbook.md`](docs/agent-playbook.md)。  
Cursor 规则：[`.cursor/rules/mau-android-agent.mdc`](.cursor/rules/mau-android-agent.mdc)。  
黄金任务：[`docs/eval-golden.md`](docs/eval-golden.md)。

---

## Grounder 模型

| 模型 | 说明 |
|------|------|
| `gui-plus-2026-02-26` | 推荐默认（DashScope） |
| `gui-plus` | DashScope 别名族 |
| `glm-4.6v-flash` | 生产支持（智谱） |
| `glm-4.6v-flashx` | 开通计费后可用 |

---

## 示例

- 携程北京民宿（分阶段 plan）：[`docs/examples/ctrip-beijing-homestay.md`](docs/examples/ctrip-beijing-homestay.md)
- Plan JSON：[`docs/examples/plans/`](docs/examples/plans/)
- 滴滴查价 recipe + 门禁：[`docs/recipes/didi.md`](docs/recipes/didi.md)
- Host TaskState 形状：[`docs/examples/task-state.example.json`](docs/examples/task-state.example.json)

## 安全

进入支付 / 提交订单页 → `NEED_HUMAN` 或 `BLOCKED_BY_POLICY`，循环停止，不要强行点击。设置里的「钱包与支付」等**不算**支付页。

## 目录结构

```text
scripts/
  mumu-adb.sh              # MuMu ADB 串号助手
  mau-mcp-with-mumu.sh     # MCP 入口：探测串号后执行 mau-mcp
  resolve-adb-serial.sh    # 保活串号 / 重选无线口
src/mano_android_use/
  session.py grounder.py safety.py tree.py
  run_loop.py run_plan.py success_check.py
  mcp_server.py cli.py
docs/
  agent-playbook.md acceptance.md plan-next.md
  recipes/ examples/ eval-*.md
```

## 相关链接

- Core 库：[jimmywang2020/mano](https://github.com/jimmywang2020/mano)（`v0.1.4`）
- 验收清单：[`docs/acceptance.md`](docs/acceptance.md)
- 路线图（含已完成项）：[`docs/plan-next.md`](docs/plan-next.md)
