from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_i18n_sync import (
    check_sync,
    discover_source_docs,
    format_report,
    mapped_zh_path,
)


def test_discover_source_docs_finds_all_mapped_sources(tmp_path: Path) -> None:
    """Verify that discover_source_docs finds docs, benchmarks, fixtures, and scripts."""
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")

    contract = tmp_path / "docs" / "contract.md"
    contract.parent.mkdir(parents=True)
    contract.write_text("# Contract\n", encoding="utf-8")

    bm1_readme = tmp_path / "benchmarks" / "bm1" / "README.md"
    bm1_readme.parent.mkdir(parents=True)
    bm1_readme.write_text("# BM1\n", encoding="utf-8")

    ds_readme = tmp_path / "benchmarks" / "bm1" / "dataset" / "README.md"
    ds_readme.parent.mkdir(parents=True)
    ds_readme.write_text("# DS\n", encoding="utf-8")

    fx1_readme = tmp_path / "tests" / "fixtures" / "fx1" / "README.md"
    fx1_readme.parent.mkdir(parents=True)
    fx1_readme.write_text("# FX\n", encoding="utf-8")

    script_doc = tmp_path / "scripts" / "dataset_card.md"
    script_doc.parent.mkdir(parents=True)
    script_doc.write_text("# Card\n", encoding="utf-8")

    sources = discover_source_docs(tmp_path)
    rels = {p.relative_to(tmp_path).as_posix() for p in sources}

    assert rels == {
        "README.md",
        "docs/contract.md",
        "benchmarks/bm1/README.md",
        "benchmarks/bm1/dataset/README.md",
        "scripts/dataset_card.md",
        "tests/fixtures/fx1/README.md",
    }


def test_discover_source_docs_excludes_docs_i18n_and_internal(tmp_path: Path) -> None:
    zh_readme = tmp_path / "docs" / "i18n" / "zh_CN" / "README.md"
    zh_readme.parent.mkdir(parents=True, exist_ok=True)
    zh_readme.write_text("# ZH\n", encoding="utf-8")

    internal_doc = tmp_path / "docs" / "internal" / "roadmap.md"
    internal_doc.parent.mkdir(parents=True, exist_ok=True)
    internal_doc.write_text("# Roadmap\n", encoding="utf-8")

    zh_doc = tmp_path / "docs" / "zh" / "index.md"
    zh_doc.parent.mkdir(parents=True, exist_ok=True)
    zh_doc.write_text("# Index\n", encoding="utf-8")

    contract = tmp_path / "docs" / "contract.md"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text("# Contract\n", encoding="utf-8")

    sources = discover_source_docs(tmp_path)
    rels = {p.relative_to(tmp_path).as_posix() for p in sources}

    assert "docs/contract.md" in rels
    assert "docs/i18n/zh_CN/README.md" not in rels
    assert "docs/internal/roadmap.md" not in rels
    assert "docs/zh/index.md" not in rels


def test_mapped_zh_path_for_root_readme(tmp_path: Path) -> None:
    src = tmp_path / "README.md"
    assert mapped_zh_path(src, tmp_path) == tmp_path / "docs" / "i18n" / "zh_CN" / "README.md"


def test_mapped_zh_path_for_docs_file(tmp_path: Path) -> None:
    src = tmp_path / "docs" / "contract.md"
    assert mapped_zh_path(src, tmp_path) == tmp_path / "docs" / "i18n" / "zh_CN" / "docs" / "contract.md"


def test_mapped_zh_path_for_nested_docs_file(tmp_path: Path) -> None:
    src = tmp_path / "docs" / "extra" / "guide.md"
    assert mapped_zh_path(src, tmp_path) == tmp_path / "docs" / "i18n" / "zh_CN" / "docs" / "extra" / "guide.md"


def test_mapped_zh_path_for_benchmark_readme(tmp_path: Path) -> None:
    src = tmp_path / "benchmarks" / "bm1" / "README.md"
    assert mapped_zh_path(src, tmp_path) == tmp_path / "docs" / "i18n" / "zh_CN" / "benchmarks" / "bm1" / "README.md"


def test_mapped_zh_path_for_dataset_readme(tmp_path: Path) -> None:
    src = tmp_path / "benchmarks" / "bm1" / "dataset" / "README.md"
    expected = tmp_path / "docs" / "i18n" / "zh_CN" / "benchmarks" / "bm1" / "dataset" / "README.md"
    assert mapped_zh_path(src, tmp_path) == expected


def test_mapped_zh_path_for_fixture_readme(tmp_path: Path) -> None:
    src = tmp_path / "tests" / "fixtures" / "fx1" / "README.md"
    expected = tmp_path / "docs" / "i18n" / "zh_CN" / "tests" / "fixtures" / "fx1" / "README.md"
    assert mapped_zh_path(src, tmp_path) == expected


def test_mapped_zh_path_for_scripts_file(tmp_path: Path) -> None:
    src = tmp_path / "scripts" / "dataset_card.md"
    expected = tmp_path / "docs" / "i18n" / "zh_CN" / "scripts" / "dataset_card.md"
    assert mapped_zh_path(src, tmp_path) == expected


def test_check_sync_reports_missing_translation(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")

    problems = check_sync(tmp_path)

    assert len(problems) == 1
    assert "README.md" in problems[0].source.name
    assert "不存在" in problems[0].status


def test_check_sync_reports_header_mismatch(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Root\n\n## Section 1\n", encoding="utf-8")
    zh = tmp_path / "docs" / "i18n" / "zh_CN" / "README.md"
    zh.parent.mkdir(parents=True)
    zh.write_text("# 根\n\n## 第一节\n\n## 第二节\n", encoding="utf-8")

    problems = check_sync(tmp_path)

    assert len(problems) == 1
    assert "h1/h2 数量不匹配" in problems[0].status
    assert "源 1/1" in problems[0].status
    assert "译 1/2" in problems[0].status


def test_check_sync_passes_when_in_sync(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Root\n\n## Section\n", encoding="utf-8")
    zh = tmp_path / "docs" / "i18n" / "zh_CN" / "README.md"
    zh.parent.mkdir(parents=True)
    zh.write_text("# 根\n\n## 节\n", encoding="utf-8")

    problems = check_sync(tmp_path)

    assert problems == []


def test_format_report_contains_source_and_zh_paths(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    problems = check_sync(tmp_path)
    report = format_report(problems, tmp_path)

    assert "| 变更文件 | 中文路径 | 状态 |" in report
    assert "README.md" in report
    assert "docs/i18n/zh_CN/README.md" in report
    assert "❌ 不存在" in report


def test_check_sync_with_explicit_sources_bypasses_discovery(tmp_path: Path) -> None:
    src = tmp_path / "README.md"
    src.write_text("# Root\n", encoding="utf-8")
    # No zh translation
    problems = check_sync(tmp_path, sources=[src])
    assert len(problems) == 1
    assert problems[0].source == src
