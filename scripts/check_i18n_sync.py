"""Check i18n documentation sync between English sources and zh_CN translations."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _count_headers(text: str) -> tuple[int, int]:
    h1 = len(re.findall(r"^# ", text, re.MULTILINE))
    h2 = len(re.findall(r"^## ", text, re.MULTILINE))
    return h1, h2


def _is_excluded_docs_path(path: Path, docs_dir: Path) -> bool:
    """Exclude docs/i18n/, docs/internal/, and docs/zh/ from source discovery."""
    rel_parts = path.relative_to(docs_dir).parts
    return any(part in {"i18n", "internal", "zh"} for part in rel_parts)


def discover_source_docs(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Discover all English source docs governed by the i18n sync contract."""
    sources: list[Path] = []

    # Root README
    root_readme = repo_root / "README.md"
    if root_readme.is_file():
        sources.append(root_readme)

    # docs/ recursively, excluding i18n/internal/zh
    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        for path in sorted(docs_dir.rglob("*.md")):
            if _is_excluded_docs_path(path, docs_dir):
                continue
            sources.append(path)

    # benchmarks/ recursively
    benchmarks_dir = repo_root / "benchmarks"
    if benchmarks_dir.is_dir():
        for path in sorted(benchmarks_dir.rglob("README.md")):
            sources.append(path)

    # tests/fixtures/ recursively
    fixtures_dir = repo_root / "tests" / "fixtures"
    if fixtures_dir.is_dir():
        for path in sorted(fixtures_dir.rglob("README.md")):
            sources.append(path)

    # scripts/ recursively
    scripts_dir = repo_root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.rglob("*.md")):
            sources.append(path)

    # Remove duplicates and sort for determinism
    seen: set[Path] = set()
    unique_sources: list[Path] = []
    for p in sources:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_sources.append(p)
    return sorted(unique_sources, key=lambda p: str(p.relative_to(repo_root)))


def mapped_zh_path(source: Path, repo_root: Path = REPO_ROOT) -> Path:
    """Return the mapped Chinese translation path for a given English source."""
    rel = source.relative_to(repo_root)
    parts = list(rel.parts)

    # README.md -> docs/i18n/zh_CN/README.md
    if parts == ["README.md"]:
        return repo_root / "docs" / "i18n" / "zh_CN" / "README.md"

    # docs/** -> docs/i18n/zh_CN/docs/**
    if parts[0] == "docs":
        return repo_root / "docs" / "i18n" / "zh_CN" / "docs" / Path(*parts[1:])

    # benchmarks/** -> docs/i18n/zh_CN/benchmarks/**
    if parts[0] == "benchmarks":
        return repo_root / "docs" / "i18n" / "zh_CN" / rel

    # tests/fixtures/** -> docs/i18n/zh_CN/tests/fixtures/**
    if parts[0] == "tests" and len(parts) > 1 and parts[1] == "fixtures":
        return repo_root / "docs" / "i18n" / "zh_CN" / rel

    # scripts/** -> docs/i18n/zh_CN/scripts/**
    if parts[0] == "scripts":
        return repo_root / "docs" / "i18n" / "zh_CN" / "scripts" / Path(*parts[1:])

    # Fallback: keep the relative path under docs/i18n/zh_CN/
    return repo_root / "docs" / "i18n" / "zh_CN" / rel


@dataclass(frozen=True)
class SyncProblem:
    source: Path
    zh_path: Path
    status: str


def check_sync(
    repo_root: Path = REPO_ROOT,
    sources: list[Path] | None = None,
) -> list[SyncProblem]:
    """Check all source docs and return a list of sync problems."""
    if sources is None:
        sources = discover_source_docs(repo_root)

    problems: list[SyncProblem] = []
    for source in sources:
        zh = mapped_zh_path(source, repo_root)
        if not zh.is_file():
            problems.append(
                SyncProblem(
                    source=source,
                    zh_path=zh,
                    status="❌ 不存在",
                )
            )
            continue

        src_text = source.read_text(encoding="utf-8")
        zh_text = zh.read_text(encoding="utf-8")
        src_h1, src_h2 = _count_headers(src_text)
        zh_h1, zh_h2 = _count_headers(zh_text)

        if src_h1 != zh_h1 or src_h2 != zh_h2:
            problems.append(
                SyncProblem(
                    source=source,
                    zh_path=zh,
                    status=f"⚠️ h1/h2 数量不匹配 (源 {src_h1}/{src_h2} vs 译 {zh_h1}/{zh_h2})",
                )
            )

    return problems


def format_report(
    problems: list[SyncProblem],
    repo_root: Path = REPO_ROOT,
) -> str:
    """Format a Markdown report table for the given problems."""
    lines: list[str] = []
    lines.append("| 变更文件 | 中文路径 | 状态 |")
    lines.append("|---|---|---|")
    for problem in problems:
        src_rel = problem.source.relative_to(repo_root).as_posix()
        zh_rel = problem.zh_path.relative_to(repo_root).as_posix()
        lines.append(f"| {src_rel} | {zh_rel} | {problem.status} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check i18n documentation sync for zh_CN translations."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root path",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with non-zero code if problems are found",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    problems = check_sync(repo_root)

    if not problems:
        print("All i18n documentation is in sync.")
        return 0

    if args.format == "table":
        print(format_report(problems, repo_root))
    else:
        import json

        data = [
            {
                "source": str(p.source.relative_to(repo_root).as_posix()),
                "zh_path": str(p.zh_path.relative_to(repo_root).as_posix()),
                "status": p.status,
            }
            for p in problems
        ]
        print(json.dumps(data, indent=2, ensure_ascii=False))

    return 1 if args.exit_code else 0


if __name__ == "__main__":
    raise SystemExit(main())
