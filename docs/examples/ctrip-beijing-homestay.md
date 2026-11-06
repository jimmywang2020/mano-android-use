# Acceptance sample: 携程 · 北京民宿 ≈¥400/天

Uses optional **`success_check`** so `GOAL_REACHED` is not only the model saying
`terminate:success`.

**Prefer staged plan** (generic A/B/C — same runner as 美团粿条):

[`plans/ctrip-beijing-homestay.json`](plans/ctrip-beijing-homestay.json)

```bash
export MANO_DEVICE_SERIAL=<phone-or-mumu-serial>
uv run mau run-plan docs/examples/plans/ctrip-beijing-homestay.json
```

Meituan takeout twin (data only): [`plans/meituan-guotiao-takeout.json`](plans/meituan-guotiao-takeout.json).

| Role | Value |
|------|--------|
| App package | `ctrip.android.view` |
| Soft goal (VLM) | 搜北京民宿，价格约 400 元/天左右；**不要下单/支付** |
| Hard check | `package=ctrip.android.view` + labels 含「北京」且含「民宿」或「客栈」或「酒店」 |

价格「约 400」留给模型导航；树断言不钉死具体金额（列表常显示区间/活动价）。

## CLI

```bash
eval "$(bash scripts/mumu-adb.sh)"   # or export MANO_DEVICE_SERIAL=<phone>
# phone already paired: export MANO_DEVICE_SERIAL=10.10.50.144:<port>

uv run mau ready

uv run mau run \
  "在携程搜索北京的民宿或客栈，浏览价格大约每天400元左右的结果列表；不要下单或支付" \
  --package ctrip.android.view \
  --max-steps 20 \
  --success-package ctrip.android.view \
  --success-label-all 北京 \
  --success-label 民宿 \
  --success-label 客栈 \
  --success-label 酒店
```

`labels_any` = 民宿|客栈|酒店（任一即可）；`labels_all` = 必须含「北京」。

期望：`status=GOAL_REACHED` 且 `success_verdict.ok=true`，`reason` 为
`success_check satisfied` 或 `terminate:success+success_check`。

默认 **只在 compact `summary` 上匹配**（避免首页 XML 里埋着「北京」误报）。  
已跑通样例：约 9 步进入「北京」+「民宿」查询页即 `GOAL_REACHED`；约 ¥400 的列表浏览仍靠 goal 引导，可再加
`--success-label-all ¥` 等收紧（视 UI 文案而定）。

若进支付/提交页 → `NEED_HUMAN` / `BLOCKED_BY_POLICY`（仍算安全闸通过）。

## MCP

```text
android_run(
  goal="在携程搜索北京的民宿或客栈，浏览约400元/天的结果；不要下单或支付",
  package="ctrip.android.view",
  max_steps=20,
  success_package="ctrip.android.view",
  success_labels_all="北京",
  success_labels_any="民宿,客栈,酒店"
)
```

## Notes

- 需已安装携程；中文输入需 AdbKeyboard。
- ColorOS 登录/权限弹窗可能需人点一次。
- Reload MCP after code update so the new parameters appear.
