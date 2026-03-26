# 快速开始

## 环境要求

- Python >= 3.13
- Windows/Linux/macOS
- `uv` 包管理器

## 安装

1. 克隆仓库：
```bash
git clone https://github.com/Mtrya/astro-reason.git
cd astro-reason
```

2. 使用 uv 安装依赖：
```bash
uv sync
```

## 基础使用

### 验证解决方案

每个基准测试都有独立的验证器（verifier），用于评估解决方案的质量。

#### SPOT-5 示例

```python
from benchmarks.spot5.verifier import SPOT5Verifier

# 加载验证器
verifier = SPOT5Verifier("benchmarks/spot5/dataset/11.spot")

# 加载解决方案
solution_path = "path/to/solution.spot_sol.txt"
result = verifier.verify(solution_path)

print(f"Profit: {result['profit']}")
print(f"Weight: {result['weight']}")
print(f"Valid: {result['is_valid']}")
```

#### SatNet 示例

```python
from benchmarks.satnet.verifier import SatNetVerifier

# 加载验证器
verifier = SatNetVerifier("benchmarks/satnet/dataset/problems.json")

# 加载解决方案
solution_path = "benchmarks/satnet/dataset/W10_2018_solution.json"
result = verifier.verify(solution_path)

print(f"Total Hours: {result['total_hours']}")
print(f"Request Coverage: {result['request_coverage']}")
```

### 运行测试

针对特定基准运行测试：

```bash
# SPOT-5 验证器测试
uv run pytest tests/benchmarks/test_spot5_verify.py

# SatNet 验证器测试
uv run pytest tests/benchmarks/test_satnet_verifier.py

# AEOSbench 验证器测试
uv run pytest tests/benchmarks/test_aeosbench_verifier.py
```

## 数据格式

不同基准测试使用不同的数据格式，主要包括：

### YAML 格式（stereo_imaging, regional_coverage 等）

```yaml
# satellites.yaml
satellites:
  - name: "SAT1"
    tle: "1 12345U 00000AAA 00 0000 00000-0 00000-0 0 9999"
    
# targets.yaml
targets:
  - name: "TARGET1"
    lat: 45.0
    lon: -120.0
```

### JSON 格式（satnet）

```json
{
  "W10_2018": [
    {
      "subject": 521,
      "duration": 1.0,
      "resources": [["DSS-34"], ["DSS-36"]],
      "time_window_start": 1520286007,
      "time_window_end": 1520471551
    }
  ]
}
```

### .spot 格式（SPOT-5）

自定义文本格式，详见 [SPOT-5 基准测试文档](benchmarks/spot5.md)。

## 评估指标

各基准测试的主要评估指标：

| 基准 | 主要指标 |
|-----|---------|
| stereo_imaging | stereo_coverage（立体覆盖比例） |
| regional_coverage | coverage_percentage（区域覆盖比例） |
| aeosbench | completion_rate（任务完成率） |
| spot5 | profit（总利润） |
| latency_optimization | latency_min/max/mean（延迟统计） |
| revisit_constellation | mean/max_revisit_gap_hours（平均/最大重访间隔） |
| satnet | total_hours（总通信时长） |
