# AstroReason-Bench 文档

AstroReason-Bench 是一个用于评估大语言模型（LLM）代理在航天任务设计与规划问题上的基准核心仓库。项目旨在为航天领域提供标准化、算法无关的基准测试，类似于 AI 领域的 ImageNet 和 GLUE。

## 项目目标

**航天领域缺乏严格、标准化的算法无关基准测试。** 虽然 AI 领域有 ImageNet 和 GLUE，但航天任务设计仍然缺乏围绕明确定义的问题和可验证评分的共享评估套件。

本仓库专注于：
- **数据集**：规范的基准测试实例
- **验证器**：独立的验证和评分逻辑
- **可复现性工具**：可选的基准本地生成器和可视化工具

## 核心特性

- **算法无关**：基准定义问题和验证方式，不限制解决问题的方法
- **独立运行**：每个基准完全自包含，不依赖其他基准
- **可复现**：可选的生成器可以在适当时重新创建或扩展数据集
- **无解决方案核心**：解决方案和基线位于外部仓库

## 支持的基准测试

| 基准名称 | 问题类型 | 描述 |
|---------|---------|------|
| [stereo_imaging](benchmarks/stereo_imaging.md) | 立体成像调度 | 规划卫星观测以获取满足立体几何约束的目标图像对 |
| [regional_coverage](benchmarks/regional_coverage.md) | 区域覆盖调度 | 最大化卫星对指定地理区域的覆盖率 |
| [aeosbench](benchmarks/aeosbench.md) | 敏捷卫星星座调度 | 使用 Basilisk 仿真分配任务以最大化完成率 |
| [spot5](benchmarks/spot5.md) | 卫星拍摄调度 | 源自法国 CNES 和 ROADEF 2003 挑战的约束优化问题 |
| [latency_optimization](benchmarks/latency_optimization.md) | 通信延迟优化 | 设计卫星中继网络以最小化地面站间通信延迟 |
| [revisit_optimization](benchmarks/revisit_optimization.md) | 重访优化 | 最小化目标观测的最大间隔 |
| [satnet](benchmarks/satnet.md) | 深空网络调度 | 源自 NASA/JPL DSN 的地面站天线时间分配 |

## 快速开始

### 环境要求

- Python >= 3.13
- 使用 `uv` 进行环境管理

### 安装

```bash
uv sync
```

### 运行测试

针对特定基准运行测试：

```bash
uv run pytest tests/benchmarks/test_spot5_verify.py
uv run pytest tests/benchmarks/test_satnet_verifier.py
uv run pytest tests/benchmarks/test_aeosbench_verifier.py
```

## 文档目录

- [项目结构](structure.md) - 仓库目录结构说明
- [快速开始](getting-started.md) - 环境配置和基础使用
- [基准测试详情](benchmarks/) - 各基准测试的详细文档
