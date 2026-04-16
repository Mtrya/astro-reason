# Revisit Constellation 测试 Fixtures

本目录包含 `revisit_constellation` 验证器的已提交端到端 fixtures。

## 目的

Fixture 套件补充了 [`tests/benchmarks/test_revisit_constellation_verifier.py`](../../benchmarks/test_revisit_constellation_verifier.py) 中聚焦的单元风格验证器测试。这些 fixtures 通过真实的 `assets.json`、`mission.json` 和 `solution.json` 输入来演练当前的 benchmark 契约。

目标不是穷举覆盖验证器的每个分支。目标是锁定一小部分具有代表性的端到端结果：

- 一个无观测的合法测试实例
- 一个有一次成功观测的合法测试实例
- 一个机动时间非法的非法测试实例

该套件有意与当前固定采样验证器对齐。它不试图指定未来基于事件的几何行为。

## Fixtures

### `zero_observation/`

一颗卫星且未调度动作的合理解。验证器应返回完整时域的重访间隔。

### `single_observation_valid/`

带有一次成功观测的合理解。这在已提交 fixture 中锚定了单次观测的指标路径。

### `maneuver_conflict_invalid/`

两次观测排得太近，导致姿态模型无法完成机动和稳定的非法解。

## Fixture 结构

每个 fixture 目录包含：

```text
fixture_name/
├── assets.json
├── mission.json
├── solution.json
└── expected.json
```

## `expected.json` 契约

验证器测试将 `expected.json` 视为部分断言契约：

- `is_valid` 是必需的。
- `metrics` 作为递归子集进行比较，浮点值使用近似比较。
- `errors` 和 `warnings` 可提供用于精确匹配。
- `errors_contain` 和 `warnings_contain` 可提供用于子字符串检查。
- `error_count` 和 `warning_count` 可用于锁定列表长度。

这使得非法 fixture 的期望即使在错误措辞稍有变化时也能保持稳定，同时仍然保留端到端裁决覆盖。
