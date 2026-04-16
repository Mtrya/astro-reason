# AstroReason-Bench

AstroReason-Bench 是一个用于评估 LLM 代理在航天任务设计与规划问题上的基准核心仓库。

当前分支仍在积极开发中，我们会持续扩展基准子任务集，并将 benchmark 与解决方案实现解耦。如需复现当前论文中的结果，请使用 `v1` 分支，该分支中 benchmark 与解决方案仍然耦合。独立的解决方案仓库已列入计划，将在未来发布。

## 为什么做这个项目？

**航天领域缺乏严格、标准化、算法无关的基准测试。** 人工智能领域有 ImageNet 和 GLUE，但航天任务设计仍然缺少围绕明确定义的问题和可验证评分构建的共享评估套件。

本仓库专注于：

- **数据集（Datasets）**：规范的 benchmark 实例
- **验证器（Verifiers）**：独立的验证与评分逻辑
- **可复现性工具**：可选的 benchmark 本地生成器与可视化工具

任何方法都可以被评估：LLM 代理、元启发式算法、强化学习系统，或人类专家。本仓库定义的是 benchmark，**不**包含解决方案实现。

## 仓库结构

```text
astro-reason/
├── benchmarks/{name}/
│   ├── dataset/              # 问题实例
│   ├── verifier.py           # 或 verifier/run.py
│   ├── visualizer.py         # 可选，或 visualizer/run.py
│   ├── generator.py          # 可选，或 generator/run.py
│   └── README.md             # 问题说明与文件格式
└── tests/
    └── benchmarks/           # 针对验证器与 benchmark 工具的聚焦测试
```

## Benchmark 设计原则

- **算法无关**：benchmark 定义问题与验证方式，不限制求解方法。
- **独立运行**：每个 benchmark 自包含，不依赖其他 benchmark。
- **可复现**：在适当场景下，可选的生成器可以重建或扩展数据集。
- **无解决方案核心**：解决方案与基线位于本仓库之外。

## 环境

本项目使用 `uv` 进行环境管理。为确保验证器完整性，请运行：

```bash
uv run pytest
```

## 状态

当前优先事项包括
- 完善多个 benchmark，
- 以及在 [AstroReason-Solvers](https://github.com/Mtrya/AstroReason-Solvers) 中实现求解器。
