这些 fixtures 用于锁定独立的 `relay_constellation` 验证器行为。

原则：

- 保持测试实例微小且易于理解
- 每个 fixture 优先只覆盖一种行为
- 仅断言稳定、定义行为的报告字段
- 使用规范的 benchmark 测试实例文件：
  - `manifest.json`
  - `network.json`
  - `demands.json`
  - `solution.json`
  - `expected.json`

Fixture 集合：

- `full_service_valid`
  - 一个需求、一颗既有的卫星（backbone satellite）、完全服务
- `served_time_only_latency_valid`
  - 一个需求、部分服务、延迟仅在被服务样本上计算
- `ground_visibility_invalid`
  - 调度的地面链路未通过几何验证
- `isl_occultation_invalid`
  - 调度的 ISL 未通过地球遮挡验证
- `concurrency_cap_invalid`
  - 几何上可行的动作超出并发上限
- `contention_deterministic_valid`
  - 两个需求竞争同一瓶颈边，确定性分配选择其一
- `ground_transit_forbidden_valid`
  - 通过中间地面端点的明显路由不被视为服务
