# Agent playbook — mano-android-use

How Cursor / Codex (or any MCP host) should drive this project. Runtime copy also
appears in `ready.tips` and MCP tool descriptions.

## Always

1. Call `doctor` then `ready` before a long task. Read `tips[]`, `screen`, `text_backend`.
2. Keep `MANO_DEVICE_SERIAL` current (wireless debug **ports change**).
3. Device must be **awake and unlocked**. `android_run` sends one `KEYCODE_WAKEUP`; it does **not** unlock.

## Open an app

| Situation | Do this |
|-----------|---------|
| Package known (e.g. 哔哩哔哩 → `tv.danmaku.bili`) | `android_run(goal=..., package="tv.danmaku.bili")` or `launch_app` |
| App on desktop, package unknown | `observe` / `find` then `tap`, or ask human for package |
| Avoid | Browser address bar + Chinese `type` just to open an installed app |

## Chinese text

- Requires OpenATX **AdbKeyboard** (`com.github.uiautomator/.AdbKeyboard`).
- If `ready.text_backend.available` is false: **launch/tap/swipe only**; do not `type_text` / goals that need typing.
- Install APK via `adb install`; ColorOS「继续安装」/防护弹窗 → `observe`+`tap` or human — **not** `android_run`.

## Safety

- Payment / submit screens → `NEED_HUMAN` or `BLOCKED_BY_POLICY`. Stop; do not force.
- Settings rows like「钱包与支付」are **not** payment (heuristic tightened in mau).

## Wireless phone (ColorOS example)

```bash
adb pair <配对IP>:<配对端口> <配对码>
adb connect <连接IP>:<连接端口>
export MANO_DEVICE_SERIAL=<连接IP>:<连接端口>
uv run mau ready
```

Update `~/.cursor/mcp.json` `env.MANO_DEVICE_SERIAL` the same way; bump `MCP_REV` if tools look stale.

## Tool choice

| Goal | Tool |
|------|------|
| Health / tips | `ready` |
| One-shot UI goal | `android_run` (+ optional `success_check`) |
| Fine-grained | `observe` → `find` / `tap` / `swipe` / `type_text` |
| Debug journal | `journal_tail` |

## success_check (prefer for “正确”)

Pass `success_package` / `success_labels_any` / `success_labels_all` so
`GOAL_REACHED` requires an external screen assertion, not only model terminate.

Example: [docs/examples/ctrip-beijing-homestay.md](examples/ctrip-beijing-homestay.md).

## Out of scope for mau

- Installing / approving third-party APKs as a product feature
- Pattern/password unlock
- mano Core Pack / WeChat entry (later phases)
