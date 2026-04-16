# Revisit Constellation 数据集

本目录包含 `revisit_constellation` benchmark 的规范提交数据集。

## 布局

- `index.json`
- `example_solution.json`
- `cases/<split>/<case_id>/assets.json`
- `cases/<split>/<case_id>/mission.json`

每个案例目录仅包含验证器使用的两个规范机器可读文件。`index.json` 记录划分感知的案例路径以及 `example_smoke_case`，用于将 `example_solution.json` 与一个提交案例配对。`example_solution.json` 是一个最小可运行解决方案（与普通提交的 schema 相同），用于验证器冒烟测试；这些不是基线。

## 规范生成

本提交数据集旨在通过以下命令重建：

```bash
uv run python -m benchmarks.revisit_constellation.generator.run \
  benchmarks/revisit_constellation/splits.yaml
```

生成器通过 `kagglehub` 自动下载文档化的源数据集，默认将原始源数据存储到 `dataset/source_data/` 下，然后重建规范案例。提交的数据集形状契约位于 [splits.yaml](../splits.yaml) 中；操作型刷新控制项如 `--download-dir` 和 `--force-download` 仍是 CLI 选项。

源数据集：

- world cities: `juanmah/world-cities`
