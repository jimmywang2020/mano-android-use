# Recipe: DiDi 查价（GoalCard / plan）

Host TaskState for「查到目的地预估价、停在叫车前」— mau does not own the recipe;
pass it as `android_run_plan` stages or several short `android_run`s.

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

## Preferred plan

[`../examples/plans/didi-airport-carpool-vs-special.json`](../examples/plans/didi-airport-carpool-vs-special.json)
（深圳机场；C 已收紧）。同类：[`didi-fengye-carpool-vs-special.json`](../examples/plans/didi-fengye-carpool-vs-special.json)。

较松的 A/B 对照夹具：[`ab-didi-xiangmihu-fare.json`](../examples/plans/ab-didi-xiangmihu-fare.json)（易在推荐列表假完成，勿当生产模板）。

### Stages

1. **open** — warm package，关广告，落地可打车首页（`您想去哪里`）
2. **dest** — **type/选点** 设终点；过关条件用报价态信号（`选路线` / `一口价` / `未拼成`），**禁止**仅靠地名子串（推荐/历史里的「香蜜湖」会假完成）
3. **fare** — `labels_all: ["未拼成", "一口价"]` + `labels_any` 特价类；可读拼车与特惠/惊喜价；永不点呼叫

## 验收结论（U2 同机，2026-11-19）

| 轮次 | 终点 | 判定 |
|------|------|------|
| 香蜜湖 | 有 | **有条件**：终态价真，但 B 在「请输入终点」+推荐里命中「香蜜湖」假完成；C 靠后续 VLM 补洞 |
| 枫叶健身 | 有 | B 真 type+选点；C 仍偏松（单「一口价」即过） |
| **深圳机场 + 清历史 + 收紧 C** | 有 | **通过**：清历史后 type「深圳机场」→ 选 T3 → C 同屏命中 `未拼成`+`一口价`+`特惠快车` |

机制侧（脏 summary / 假 terminate）在三轮均立住：systemui 过滤、check 在 BACK 前、`terminate` 否决、`fare_seen`。

### 已知坑（Host / mau）

- **清历史**：搜索页下滑可见「清空历史记录」→ 确认「立即清空」。勿用松 `success_labels_any` 含「请输入终点」的 `android_run` 冒充已清空。
- **无坐标 click**：旧行为会整 stage `ERROR`；现应 skip 并重试（见 run_loop）。
- **费用串台**：长 MCP session 曾把多任务 journal 累进一份 `cost_report`。现 `android_run`/`android_run_plan` 会 `begin_run` 换 `run_id`，且 cost 按当次 `history` 计。
- 终态报价 XML 常 **不含** 终点地名（只在地图像素上）；不要用终态树验证「香蜜湖/机场」字符串。

## Resume

On `TIME_BUDGET` / `STUCK` / `ERROR`，读 `resume`/`continue_hint`，填 `do.*`（omit `package=`，`cold_start=false`）。
若 `progress.fare_seen`，不要 HOME / force-stop。

## Verified promotion (optional, Host-side)

Only after a human-confirmed success: promote short `when` → `tree_hints` /
`success_check` labels into this recipe. Do not auto-write a single run into truth.
