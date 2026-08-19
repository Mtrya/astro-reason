# Revisit Constellation 数据集

本目录包含 `revisit_constellation` benchmark 的规范提交数据集。

## 布局

- `index.json`
- `example_solution.json`
- `cases/<split>/<case_id>/assets.json`
- `cases/<split>/<case_id>/mission.json`

每个测试实例目录仅包含验证器使用的两个规范机器可读文件。`index.json` 记录子集感知的测试实例路径以及 `example_smoke_case`，用于将 `example_solution.json` 与一个提交测试实例配对。`example_solution.json` 是一个最小可运行解（与普通提交的 schema 相同），用于验证器冒烟测试；这些不是基线。

## 规范生成

本提交数据集旨在通过以下命令重建：

```bash
uv run python -m benchmarks.revisit_constellation.generator.run \
  benchmarks/revisit_constellation/splits.yaml
```

生成器默认将 vendored 的 world-cities 快照（`../generator/world_cities_snapshot.csv`，由文档化的 Kaggle 数据集第 8 版规范化而来）暂存到 `dataset/source_data/` 下，然后无需网络访问即可重建规范测试实例。提交的数据集形状契约位于 [splits.yaml](/benchmarks/revisit_constellation/splits.yaml) 中；操作型暂存控制项如 `--download-dir` 仍是 CLI 选项。

源数据集：

- world cities: `juanmah/world-cities` 第 8 版（vendored 为 `../generator/world_cities_snapshot.csv`）
