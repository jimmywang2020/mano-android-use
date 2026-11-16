# Agent playbook — mano-android-use

How Cursor / Codex (or any MCP host) should drive this project. Runtime copy also
appears in `ready.tips` and MCP tool descriptions.

**Principle:** Host picks **goal/plan**; mau **orchestrates** the loop; Grounder
**sees screenshots**; **L0** is the only path that hits the device.

## Always

1. Call `doctor` then `ready` before a long task. Read `tips[]`, `screen`, `text_backend`.
2. Wireless debug **ports change**. Prefer MCP command `scripts/mau-mcp-with-mumu.sh` (auto-resolves via `resolve-adb-serial.sh`); do not pin a dead `ip:port` in MCP env. CLI: `eval "$(bash scripts/resolve-adb-serial.sh)"`.
3. Device must be **awake and unlocked**. `android_run` sends one `KEYCODE_WAKEUP`; it does **not** unlock.

## Default path (multi-step)

```text
ready → (launch_app | android_run package=…) → android_run | android_run_plan
```

| Goal | Tool |
|------|------|
| Health / tips | `ready` |
| One-shot UI goal | **`android_run`** (+ optional `success_check`) |
| Long / multi-stage goal | **`android_run_plan`** (short stages + per-stage `success_check`) |
| Debug journal | `journal_tail` |

Do **not** chain `propose_action` → `tap` (or `propose_action(execute=true)`) as the main loop.
That duplicates mau’s B-path and causes long Host round-trips / empty spinning.

`propose_action(execute=true)` is **deprecated** (requires `MAU_ALLOW_PROPOSE_EXECUTE=1`).

## Open an app

| Situation | Do this |
|-----------|---------|
| Package known (e.g. 哔哩哔哩 → `tv.danmaku.bili`) | `android_run(goal=..., package="tv.danmaku.bili")` or `launch_app` |
| App on desktop, package unknown | `observe` / `find` then `tap`, or ask human for package |
| Avoid | Browser address bar + Chinese `type` just to open an installed app |

## L0 correction only

Use `observe` → `find` / `tap` / `swipe` / `type_text` / `press_button` for:

- APK install / ColorOS「继续安装」dialogs
- One-off nudge after a failed run
- Debugging coordinates

Not for multi-step product goals.

## Chinese text

- Requires OpenATX **AdbKeyboard** (`com.github.uiautomator/.AdbKeyboard`).
- If `ready.text_backend.available` is false: **launch/tap/swipe only**; do not `type_text` / goals that need typing.
- Install APK via `adb install`; ColorOS「继续安装」/防护弹窗 → `observe`+`tap` or human — **not** `android_run`.

## Safety

- Payment / submit screens → `NEED_HUMAN` or `BLOCKED_BY_POLICY`. Stop; do not force.
- Settings rows like「钱包与支付」are **not** payment (heuristic tightened in mau).
- Prefer MCP/CLI L0 (`tap` etc.) over shell `adb input tap` so safety + journal stay intact.

## Wireless phone (ColorOS example)

```bash
adb pair <配对IP>:<配对端口> <配对码>
adb connect <连接IP>:<连接端口>
export MANO_DEVICE_SERIAL=<连接IP>:<连接端口>
uv run mau ready
```

Update `~/.cursor/mcp.json` `env.MANO_DEVICE_SERIAL` the same way; bump `MCP_REV` if tools look stale.

## success_check (prefer for “正确”)

Pass `success_package` / `success_labels_any` / `success_labels_all` so
`GOAL_REACHED` requires an external screen assertion, not only model terminate.

Use **narrow** labels (avoid matching too early). Prefer staged plans over one huge goal
with a loose check.

Example: [docs/examples/ctrip-beijing-homestay.md](examples/ctrip-beijing-homestay.md).

## Staged plans (A/B/C) — app-agnostic

Long goals → split into stages, each with its own `goal` + `success_check` and a
modest `max_steps` (avoid burning budget on empty spinning).

Runner: `mau run-plan <plan.json>` or MCP `android_run_plan`.

| App | Plan JSON |
|-----|-----------|
| 携程北京民宿 | [examples/plans/ctrip-beijing-homestay.json](examples/plans/ctrip-beijing-homestay.json) |
| 美团粿条外卖 | [examples/plans/meituan-guotiao-takeout.json](examples/plans/meituan-guotiao-takeout.json) |

Same code path; only package / labels / goals change. Host can also call `android_run` three times by hand.

Between stages, `PlanState` injects into the next stage prompt: completed stage ids,
last screen summary, and **do not redo completed stages** (no unnecessary relaunch /
re-select city). This is thin continuity — not a full LangGraph.

## Out of scope for mau

- Installing / approving third-party APKs as a product feature
- Pattern/password unlock
- mano Core Pack / WeChat entry (later phases)
