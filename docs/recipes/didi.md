# Recipe: DiDi 查价（GoalCard / plan）

Host TaskState for「查到目的地预估价、停在叫车前」— mau does not own the recipe;
pass it as `android_run_plan` stages or several short `android_run`s.

## Recipe 门禁（成功谓词）

**记忆管接着干；门禁管算不算干完。** 假 GOAL 来自契约太松，不是 `progress` OR-merge 能救。

| 规则 | 生产要求 |
|------|----------|
| 终态 stage | 用 **`labels_all`**（同时见 `未拼成` + `一口价`），勿单靠松 `labels_any` |
| 设终点 stage | 过关看 **报价态信号**（`选路线` / `一口价` / `未拼成`…），**禁止**仅靠地名子串 |
| 反例禁词 | **`forbid_labels: ["请输入终点"]`** — 搜索/推荐页即使出现「香蜜湖」也不能过 |
| Host 纪律 | 禁止把松 OR（含地名 / 「请输入终点」）写进生产 `success_check` |
| VLM terminate | 仅候选；门禁可否决 |

API：`success_check.forbid_labels`（别名 `require_absent`）；MCP `success_forbid_labels`；CLI `--success-forbid-label`。

## GoalCard

| Field | Example |
|-------|---------|
| `intent` | 分别查看拼车与特价/特惠预估价 |
| `params.dest` | 深圳机场 / 枫叶健身 / … |
| `package` | `com.sdu.didi.psnger` |
| `stop_when` | **同时**见拼车价（`未拼成`）与一口价（`labels_all`） |
| `forbidden` | 呼叫、确认叫车、支付、HOME 冷启续跑 |
| `hints` | `关闭弹窗` / `您想去哪里` / `特价拼车` / `特惠快车` |

`success_check` defaults to **foreground tree** (systemui filtered). Do **not** rely on
raw `summary` alone under ColorOS U2 dumps.

## Preferred plan（production）

[`../examples/plans/didi-airport-carpool-vs-special.json`](../examples/plans/didi-airport-carpool-vs-special.json)
（`role: production`）。同类：[`didi-fengye-carpool-vs-special.json`](../examples/plans/didi-fengye-carpool-vs-special.json)。

**夹具（勿当生产）**：[`ab-didi-xiangmihu-fare.json`](../examples/plans/ab-didi-xiangmihu-fare.json)
（`role: fixture`, `production: false` — 故意松 OR，易在推荐列表假完成；仅 observe A/B）。

### Stages

1. **open** — warm package，关广告，落地可打车首页（`您想去哪里`）
2. **dest** — type/选点；`labels_any` = 报价信号 + **`forbid_labels: [请输入终点]`**
3. **fare** — `labels_all: ["未拼成", "一口价"]` + `labels_any` 特价类 + 同上 forbid；永不点呼叫

## 验收结论（U2 同机，2026-11-19）

| 轮次 | 终点 | 判定 |
|------|------|------|
| 香蜜湖（松夹具） | 有 | **有条件**：终态价真，但 B 在「请输入终点」+推荐里命中「香蜜湖」假完成 |
| 枫叶健身（旧松 C） | 有 | B 真 type+选点；旧 C 单「一口价」即过 → **现已对齐 airport 门禁** |
| **深圳机场 + 清历史 + 收紧 C** | 有 | **通过**：清历史后 type「深圳机场」→ 选 T3 → C 同屏 `未拼成`+`一口价` |

机制侧：systemui 过滤、check 在 BACK 前、`terminate` 否决、`fare_seen`、`task_patch` / `progress_json`。

### 已知坑（Host / mau）

- **清历史**：搜索页下滑「清空历史记录」→「立即清空」。勿用含「请输入终点」的松 check 冒充已清空。
- **无坐标 click**：skip 并重试（见 run_loop）。
- **费用串台**：`begin_run` + history-scoped cost。
- 终态报价 XML 常 **不含** 终点地名；不要用终态树验证地名。

## Resume + Host TaskState

1. 合并 **`task_patch`** → Host TaskState（OR-merge `progress`；替换 `resume` / `screen_digest`）。
2. 填 `resume.do.*`：omit `package=`，`cold_start=false`，保留门禁字段。
3. 下一轮带 **`progress_json`** = TaskState.progress。
4. 若 `progress.fare_seen`，不要 HOME / force-stop。

Shape: [`../examples/task-state.example.json`](../examples/task-state.example.json)。

## Verified promotion (optional, Host-side)

Only after a human-confirmed success: promote short `when` → `tree_hints` /
`success_check` labels into a **production** plan. Never promote a fixture run that
passed on loose dest-name OR.
