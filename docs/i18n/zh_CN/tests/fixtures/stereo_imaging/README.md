# Stereo Imaging 验证器测试 Fixtures

本目录包含 `stereo_imaging` 验证器的已提交端到端 fixtures。

## 目的

Fixture 套件补充了 [`tests/benchmarks/test_stereo_imaging_verifier.py`](../../benchmarks/test_stereo_imaging_verifier.py) 中聚焦的单元风格验证器测试。这些 fixtures 通过真实的 `mission.yaml`、`satellites.yaml`、`targets.yaml` 和 `solution.json` 输入来演练当前的 benchmark 契约。

目标不是穷举覆盖验证器的每个分支。目标是锁定一小部分具有代表性的端到端结果：

- 一个无观测的合法测试实例
- 一个观测重叠的非法测试实例
- 一个机动/稳定间隙不足的非法测试实例

## Fixtures

### `empty_solution/`

零动作的合理解。验证器应返回零覆盖和零质量。

### `time_overlap_invalid/`

同一卫星上两次观测在时间上重叠的非法解。

### `slew_too_fast_invalid/`

两次观测指向不同位置且间隙为零，卫星远远来不及机动和稳定的非法解。

## Fixture 结构

每个 fixture 目录包含：

```text
fixture_name/
├── mission.yaml
├── satellites.yaml
├── targets.yaml
├── solution.json
└── expected.json
```

所有 fixtures 都使用一个最小合成数据集：一颗卫星（Pleiades-1A TLE）、一两个赤道目标、以及一个六小时时域。

## `expected.json` 契约

验证器测试将 `expected.json` 视为部分断言契约：

- `valid` 是必需的。
- `metrics` 作为递归子集进行比较，浮点值使用近似比较。
- 可以提供 `violations_contain` 作为子字符串列表，每个子字符串必须至少出现在一个违规字符串中。
- 可以提供 `violation_count` 来精确锁定违规数量。

这使得非法 fixture 的期望即使在错误措辞稍有变化时也能保持稳定，同时仍然保留端到端裁决覆盖。
