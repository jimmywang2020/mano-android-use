# Recipe: 美团外卖加购（GoalCard / plan）

Host TaskState for「点饮品进购物车、停支付前」— mau 不写死美团状态机；差异只在 plan
数据。配对：[`../examples/plans/meituan-lemon-tea-cart.json`](../examples/plans/meituan-lemon-tea-cart.json)、
[`../examples/plans/meituan-dual-drink-cart.json`](../examples/plans/meituan-dual-drink-cart.json)。

## DONE 证据（M4 世界态门禁）

**记忆管接着干；门禁管算不算干完。** 假 GOAL 常来自「搜页/菜单只见品名」。

| 规则 | 生产要求 |
|------|----------|
| 终态 stage | **`labels_all` 含世界态**：单杯 `去结算`+`已添加`；**双杯**必须 `去结算`+`已添加2件`（裸「已添加」会在 1 件上假 GOAL） |
| 品名 | 用 **`labels_any`** 表达 SKU 族（柠檬茶 / 手打柠檬…），不要单靠品名 `labels_all` |
| 加购 stage | 单杯/第一杯看 `已添加1件`；第二杯必须 `已添加2件`；**不要**用菜单「到手约」或裸「已添加」/`去结算` OR 当第二杯 DONE |
| 反例 | 搜索列表仅「柠檬茶」→ 不得 GOAL；须进店且车内证据 |
| hints | **禁止**把 `已添加` / `去结算` / `马上抢` / `支付` 放进 `tree_hints` |
| 多 SKU | 每段 **替换** hints；完成后 Host 写 `world.sku_keys` + Guard bans |
| 价带 | Host/人眼分 stage；**不做** mau UNSAT 硬门禁 |

mau 会从「已添加N件」类 a11y **建议** `progress.world.cart_count`（见
`world_evidence`）；`sku_keys` 仍由 Host 在 stage 成功后写入。

## Stages（单杯）

1. **A_enter_store** — 外卖搜索进店；DONE = `选规格` / `请输入商品名`（或明确菜单列表+规格按钮）。**不要**裸「点菜」；**不要**仅凭残车 `去结算` / `cart_count≥1` 判进店成功（Phase R5）
2. **B_add_*** — hints **SKU-first** → 选规格 → 加入购物车；`labels_any: [已添加, 去结算]`
3. **C_verify_*** — 空 hints；`labels_all: [去结算, 已添加]` + 品名 `labels_any`

## Stages（双杯）

A 进店（**须菜单证据：选规格/请输入商品名**）→ **A2_open_menu**（可选：外送/上滑露规格；`find` 已见选规格则 Host `on_done` 跳过）→ B 第一杯（`已添加1件`；若残车已是本店 1 件可用 `find` 确认后跳过重加，但仍须先完成真正进店）→ C 第二杯（**换** SKU-first hints，`已添加2件`）→ D verify（`labels_all: 去结算+已添加2件`）。

**进店一次到位（Phase R5）：** success_check 优先 `选规格`（或 `请输入商品名`）；店头「外送/自取/点菜」不够。残车 chrome 只证明「有车」，不证明「已在可点菜单」。

**进 C 前（Phase Q3，动态 hint）：**

1. `find`「奶茶」；有则 C hints 以奶茶 SKU-first。  
2. 无奶茶 → `find` 菜单上 **另一单杯**（勿与 B 的 `world.sku_keys` 重复；避开套餐/选套餐）。  
3. 再开 **一次** `android_run`（不要先空跑一轮 STUCK 再手搓 L0）。  
4. **禁止**把某店具体品名（如「林里招牌」）写死进 slots 只为「跳过 C1」——伤泛化。

**Cursor：** 用 [`../examples/slots/meituan-dual-drink.slots.json`](../examples/slots/meituan-dual-drink.slots.json) **N×短 `android_run`**（Phase O-A）；STUCK/`TIME_BUDGET` 后 **`find`/`slot_peek` → 换 hint → 短跑**，**不要** L0 连点（Phase Q1/R）。若返回 `L0_BLOCKED_AFTER_STUCK`：跟 `next`，或 `force_l0=true` 单次纠偏。不要一次 MCP `android_run_plan` 扛全程。丢包走 Phase O-B，件数以「已添加N件」为准。

**压缩编排 gap（Phase R6）：** 收到 `task_patch`/`continue_hint` 后立刻填下一短跑；`find` 仅在换页/换杯时用；禁止同 dull-hint 再开一轮空转。墙钟目标 ≲3min（对标 Q4r2 ~297s）。

## Host SlotSpec（推荐）

用同一套 `next_slot` / `on_done` 驱动双杯编排（与滴滴 SlotSpec API 相同）：

[`../examples/slots/meituan-dual-drink.slots.json`](../examples/slots/meituan-dual-drink.slots.json)
— 见 [`../examples/slots/README.md`](../examples/slots/README.md)。

## Host `progress_json` 示例（B 完成后）

```json
{
  "completed_slots": ["A_enter_store", "B_add_single_cup"],
  "world": { "cart_count": 1, "sku_keys": ["鸭屎香柠檬茶"] },
  "policy": {
    "banned_act_classes": ["open_spec", "confirm_add"],
    "banned_hint_labels": ["已添加", "去结算", "马上抢"]
  },
  "cart_seen": true
}
```

（第二杯阶段应去掉对该 SKU 的 `open_spec` 全局 ban，或只靠 `world.sku_keys` + Guard
对**已在车** target NO_OP，并为新 SKU 换 goal/hints。）

## 对照夹具

松 OR / 神抢手「马上抢」路径不算本 recipe 生产真相；支付页停靠 SafetyGateway。
