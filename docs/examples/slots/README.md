# Host SlotSpec examples (Phase M3)

Thin Host orchestration — **not** mau internals. Same Python API for every app:

```python
from mano_android_use.host_slots import load_slot_graph, next_slot, on_done, build_android_run_args

graph = load_slot_graph("docs/examples/slots/meituan-dual-drink.slots.json")
progress = {}
while True:
    slot = next_slot(graph, progress)
    if slot is None:
        break
    args = build_android_run_args(slot, progress)
    # Host: call MCP android_run(**args.to_mcp_arguments())
    # on GOAL_REACHED / verify-ok:
    progress = on_done(progress, slot)
```

| File | App |
|------|-----|
| [`meituan-dual-drink.slots.json`](meituan-dual-drink.slots.json) | Meituan dual cart |
| [`didi-airport-fare.slots.json`](didi-airport-fare.slots.json) | DiDi airport fare |

You can also `load_slot_graph("docs/examples/plans/*.json")` — stages become slots with linear `depends_on`.

`on_done` writes `completed_slots` and merges `forbid_when_done` into `world` / `policy` so the **next** slot’s hints are taken only from that SlotSpec (never inherit bare「选规格」).

**Peek next (Phase P4 / O3):** after STUCK/`TIME_BUDGET`, before the next short run:

```bash
uv run mau slot-next docs/examples/slots/meituan-dual-drink.slots.json \
  --progress-json '{"completed_slots":["A_enter_store","A2_open_menu"]}'
```

Returns `args` (MCP-ready) + `suggested_find` needles from `done_when`. MCP: `slot_peek`.
