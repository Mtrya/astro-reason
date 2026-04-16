# Regional Coverage 验证器测试 Fixtures

本目录包含 `regional_coverage` 验证器的已提交端到端 fixtures。

## 目的

Fixture 套件补充了 [`tests/benchmarks/test_regional_coverage_verifier.py`](../../benchmarks/test_regional_coverage_verifier.py) 中聚焦的单元风格验证器测试。这些 fixtures 通过真实的 `manifest.json`、`satellites.yaml`、`regions.geojson`、`coverage_grid.json` 和 `solution.json` 输入来演练当前的 benchmark 契约。

目标不是穷举覆盖验证器的每个分支。目标是锁定一小部分具有代表性的端到端结果：

- 一个带有一条成功条带的合法测试实例
- 一个合法的加权评分测试实例
- 一个无重访奖励的合法重复覆盖测试实例
- 机动、离轴边界、电池耗尽和成像占空比的非法测试实例

## Fixtures

### `single_strip_valid/`

带有一条完全覆盖一个加权样本的条带的合理解。

### `weighted_region_scoring_valid/`

只有权重较高区域被覆盖的合理解。这锁定了全局加权 `coverage_ratio`。

### `repeat_coverage_no_bonus_valid/`

两颗卫星覆盖同一采样集的合理解。第二次通过后，唯一覆盖权重不得增加。

### `slew_gap_invalid/`

同一卫星的两条条带之间没有留出足够时间机动和稳定的非法解。

### `edge_band_invalid/`

滚动角违反传感器离轴边缘带的非法解。

### `battery_depletion_invalid/`

几何上合法成像但电池状态不可行的非法解。

### `imaging_duty_limit_invalid/`

超过每轨成像占空比限制的非法解。

## Fixture 结构

每个 fixture 目录包含：

```text
fixture_name/
├── manifest.json
├── satellites.yaml
├── regions.geojson
├── coverage_grid.json
├── solution.json
└── expected.json
```

所有 fixtures 都使用一个围绕一颗固定 ICEYE TLE、小方形区域和易于理解的微小加权网格构建的最小合成数据集。

## `expected.json` 契约

验证器测试将 `expected.json` 视为部分断言契约：

- `valid` 是必需的。
- `metrics` 作为递归子集进行比较，浮点值使用近似比较。
- 可以提供 `violations_contain` 作为子字符串列表，每个子字符串必须至少出现在一个违规字符串中。
- 可以提供 `violation_count` 来精确锁定违规数量。

这使得非法 fixture 的期望即使在措辞稍有变化时也能保持稳定，同时仍然保留端到端裁决覆盖。
