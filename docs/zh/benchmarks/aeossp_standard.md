# AEOSSP Standard

`aeossp_standard` 是当前仓库中标准的敏捷地球观测调度基准。

它建模的是：

- 固定真实轨道星座
- 12 小时规划时域
- 点目标成像任务
- 验证器拥有的可见性、姿态机动和电池约束
- 事件式 `observation` 动作调度

求解器需要在任务窗口内安排观测动作，同时满足：

- 传感器类型匹配
- 连续可见性
- 最大离轴角限制
- 同星观测间的机动与稳定时间
- 全时域电池可行性

核心指标：

- `WCR`
- `CR`
- `TAT`
- `PC`

公开入口：

```bash
uv run python -m benchmarks.aeossp_standard.generator.run
uv run python -m benchmarks.aeossp_standard.verifier.run <case_dir> <solution_path>
uv run python -m benchmarks.aeossp_standard.visualizer.run case --case-dir <case_dir>
uv run python -m benchmarks.aeossp_standard.visualizer.run solution --case-dir <case_dir> --solution-path <solution_path>
```

详细公共说明请以基准目录下的
[README.md](../../../benchmarks/aeossp_standard/README.md) 为准。
