#!/usr/bin/env python3
"""Generate the Brahe skill from upstream docs and reachable source files.

Reads from vendor/brahe/ (or clones upstream) and writes a docs-preserving
skill tree to .agents/skills/brahe/.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path


SNIPPET_PATTERN = re.compile(r"^(?P<indent>\s*)--8<--\s+['\"](?P<spec>.+?)['\"]\s*$", re.MULTILINE)
MARKDOWN_LINK_PATTERN = re.compile(
    r"(?P<prefix>!?)\[(?P<text>[^\]]+)\]\((?P<target>[^)\s]+)(?P<title>\s+[^)]*)?\)"
)
TAB_HEADER_PATTERN = re.compile(r'^===\s+["\'](?P<name>.+?)["\']\s*$')
SPECIAL_BLOCK_PATTERN = re.compile(r'^(?P<marker>!!!|\?\?\?)\s+(?P<kind>\w+)?\s*(?:"?(?P<title>.+?)"?)?\s*$')
PROTECTED_OUTPUT_DIRS = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Brahe skill")
    parser.add_argument(
        "--source",
        default=None,
        help="Path to Brahe source directory (defaults to cloning from GitHub)",
    )
    parser.add_argument(
        "--output",
        default=".agents/skills/brahe",
        help="Output directory for the skill",
    )
    args = parser.parse_args()

    output = Path(args.output).resolve()

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        if args.source is None:
            temp_dir = tempfile.TemporaryDirectory(prefix="brahe-skill-source-")
            source = Path(temp_dir.name) / "brahe"
            print("Cloning Brahe from GitHub ...")
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "https://github.com/duncaneddy/brahe.git",
                    str(source),
                ],
                check=True,
            )
            print(f"Cloned to {source}")
        else:
            source = Path(args.source).resolve()
            if not source.exists():
                print(f"Source directory does not exist: {source}", file=sys.stderr)
                return 1

        if output.exists():
            if output in PROTECTED_OUTPUT_DIRS:
                print(f"Refusing to delete protected directory: {output}", file=sys.stderr)
                return 1
            shutil.rmtree(output)
        output.mkdir(parents=True)

        docs_learn = source / "docs" / "learn"
        if docs_learn.exists():
            process_docs_learn(docs_learn, output, source)

        generate_skill_index(output)

    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    print(f"Skill generated at: {output}")
    return 0


def process_docs_learn(src_dir: Path, out_root: Path, repo_root: Path) -> None:
    """Process docs/learn and copy all reachable source files under original paths."""
    markdown_files, copied_files = collect_reachable_files(src_dir, repo_root)

    for src_file in markdown_files:
        write_processed_markdown(src_file, out_root, repo_root)

    for src_file in copied_files:
        copy_repo_file(src_file, out_root, repo_root)


def collect_reachable_files(seed_dir: Path, repo_root: Path) -> tuple[list[Path], list[Path]]:
    """Return markdown docs to process plus non-markdown files to copy."""
    docs_root = repo_root / "docs"
    plots_learn_root = repo_root / "plots" / "learn"

    markdown_files: set[Path] = set()
    copied_files: set[Path] = set()
    queue: deque[Path] = deque(sorted(seed_dir.rglob("*.md")))

    while queue:
        doc_path = queue.popleft()
        if doc_path in markdown_files or not doc_path.exists():
            continue

        markdown_files.add(doc_path)
        content = doc_path.read_text(encoding="utf-8")

        for dependency in discover_snippet_dependencies(content, repo_root):
            if dependency.suffix == ".md" and dependency.is_relative_to(docs_root):
                queue.append(dependency)
            elif not is_redundant_inlined_dependency(dependency, repo_root):
                copied_files.add(dependency)

        for dependency in discover_link_dependencies(content, doc_path):
            if dependency.suffix == ".md" and dependency.is_relative_to(docs_root):
                queue.append(dependency)
            else:
                copied_files.add(dependency)

    if any(path.is_relative_to(plots_learn_root) for path in copied_files):
        brahe_theme = repo_root / "plots" / "brahe_theme.py"
        if brahe_theme.exists():
            copied_files.add(brahe_theme)

    return sorted(markdown_files), sorted(copied_files)


def discover_snippet_dependencies(content: str, repo_root: Path) -> set[Path]:
    """Find local files referenced through mkdocs snippet includes."""
    dependencies: set[Path] = set()

    for match in SNIPPET_PATTERN.finditer(content):
        target_path, _, _ = parse_snippet_spec(match.group("spec"))
        dependency = resolve_repo_relative_path(repo_root, target_path)
        if dependency.exists():
            dependencies.add(dependency)

    return dependencies


def discover_link_dependencies(content: str, doc_path: Path) -> set[Path]:
    """Find reachable local files referenced by markdown links."""
    dependencies: set[Path] = set()

    for match in MARKDOWN_LINK_PATTERN.finditer(content):
        target = match.group("target")
        if is_external_target(target):
            continue

        path_text = split_link_suffix(target)
        if not path_text:
            continue

        dependency = (doc_path.parent / path_text).resolve()
        if dependency.exists():
            dependencies.add(dependency)

    return dependencies


def is_redundant_inlined_dependency(path: Path, repo_root: Path) -> bool:
    """Return whether a snippet dependency is redundant after inlining."""
    return path.is_relative_to(repo_root / "examples") or path.is_relative_to(repo_root / "plots")


def write_processed_markdown(src_file: Path, out_root: Path, repo_root: Path) -> None:
    """Write one processed markdown file under its original repository-relative path."""
    out_file = out_root / src_file.relative_to(repo_root)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    content = src_file.read_text(encoding="utf-8")
    content = resolve_snippets(content, repo_root)
    content = filter_tabs(content)
    content = clean_mkdown_syntax(content)
    content = normalize_fenced_code_blocks(content)
    content = remove_leading_blank_lines_in_fences(content)
    content = remove_orphan_output_headers(content)

    out_file.write_text(content, encoding="utf-8")


def copy_repo_file(src_file: Path, out_root: Path, repo_root: Path) -> None:
    """Copy one repository file under its original repository-relative path."""
    out_file = out_root / src_file.relative_to(repo_root)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, out_file)


def resolve_snippets(content: str, repo_root: Path) -> str:
    """Replace --8<-- includes with inlined file contents."""

    def replacer(match: re.Match) -> str:
        indent = match.group("indent")
        file_path, start_line, end_line = parse_snippet_spec(match.group("spec"))
        target = resolve_repo_relative_path(repo_root, file_path)

        if not target.exists():
            return f"{indent}# [Included file not found: {file_path}]"

        lines = target.read_text(encoding="utf-8").splitlines()
        if start_line is not None:
            lines = lines[start_line - 1:end_line]

        return "\n".join(f"{indent}{line}" for line in dedent_lines(lines))

    return SNIPPET_PATTERN.sub(replacer, content)


def filter_tabs(content: str) -> str:
    """Remove pymdownx.tabbed Rust blocks while keeping Python content."""
    lines = content.splitlines()
    result: list[str] = []
    skipped_tab_indent: int | None = None
    kept_tab_indent: int | None = None
    kept_tab_dedent: int | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        tab_match = TAB_HEADER_PATTERN.match(stripped)
        if tab_match:
            tab_name = tab_match.group("name")
            if tab_name == "Rust":
                skipped_tab_indent = indent
                kept_tab_indent = None
                kept_tab_dedent = None
                i += 1
                continue
            if tab_name == "Python":
                kept_tab_indent = indent
                skipped_tab_indent = None
                kept_tab_dedent = None
                i += 1
                continue

            skipped_tab_indent = None
            kept_tab_indent = None
            kept_tab_dedent = None
            result.append(line)
            i += 1
            continue

        if skipped_tab_indent is not None:
            if not stripped or indent > skipped_tab_indent:
                i += 1
                continue
            skipped_tab_indent = None

        if kept_tab_indent is not None:
            if not stripped:
                result.append("")
                i += 1
                continue
            if indent > kept_tab_indent:
                if kept_tab_dedent is None:
                    kept_tab_dedent = indent
                result.append(strip_common_indent(line, kept_tab_dedent))
                i += 1
                continue

            kept_tab_indent = None
            kept_tab_dedent = None

        result.append(line)
        i += 1

    return "\n".join(result)


def clean_mkdown_syntax(content: str) -> str:
    """Remove or simplify mkdocs-material specific syntax."""
    lines = content.splitlines()
    result: list[str] = []
    plotly_depth = 0
    in_center_table = False
    special_base_indent: int | None = None
    special_dedent: int | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if stripped.startswith("<div"):
            if 'class="plotly-embed"' in stripped:
                plotly_depth += 1
                i += 1
                continue
            if 'class="center-table"' in stripped:
                in_center_table = True
                i += 1
                continue
        elif stripped.startswith("</div>"):
            if plotly_depth > 0:
                plotly_depth -= 1
                i += 1
                continue
            if in_center_table:
                in_center_table = False
                i += 1
                continue
        elif stripped.startswith("<figure"):
            plotly_depth += 1
            i += 1
            continue
        elif stripped.startswith("</figure>"):
            if plotly_depth > 0:
                plotly_depth -= 1
                i += 1
                continue

        if plotly_depth > 0:
            i += 1
            continue

        special_match = SPECIAL_BLOCK_PATTERN.match(stripped)
        if special_match:
            special_base_indent = indent
            special_dedent = None
            title = special_match.group("title") or special_match.group("kind") or "Note"
            result.append(f"**{title}**")
            i += 1
            continue

        if special_base_indent is not None:
            if not stripped:
                result.append("")
                i += 1
                continue
            if indent > special_base_indent:
                if special_dedent is None:
                    special_dedent = indent
                result.append(strip_common_indent(line, special_dedent))
                i += 1
                continue

            special_base_indent = None
            special_dedent = None

        result.append(line)
        i += 1

    return "\n".join(result)


def normalize_fenced_code_blocks(content: str) -> str:
    """Dedent indented fenced code blocks so the fence starts at column 0."""
    lines = content.splitlines()
    result: list[str] = []
    in_fence = False
    fence_indent = 0
    fence_char = ""

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if not in_fence:
            fence_match = re.match(r"(`{3,}|~{3,})(?:\s+(\S+))?", stripped)
            if fence_match:
                in_fence = True
                fence_indent = indent
                fence_char = fence_match.group(1)
                info = fence_match.group(2) or ""
                result.append(f"{fence_char}{info}" if info else fence_char)
                continue
            result.append(line)
            continue

        if stripped.startswith(fence_char):
            remainder = stripped[len(fence_char):]
            if not remainder or remainder.strip() == "":
                in_fence = False
                result.append(fence_char)
                continue

        result.append(line[fence_indent:] if line.strip() and indent >= fence_indent else line.lstrip())

    return "\n".join(result)


def remove_leading_blank_lines_in_fences(content: str) -> str:
    """Remove blank lines immediately after a fenced code opener."""
    lines = content.splitlines()
    result: list[str] = []
    in_fence = False
    strip_leading_blank = False
    fence_char = ""

    for line in lines:
        stripped = line.lstrip()

        if not in_fence:
            fence_match = re.match(r"(`{3,}|~{3,})(?:\s+(\S+))?", stripped)
            if fence_match:
                in_fence = True
                strip_leading_blank = True
                fence_char = fence_match.group(1)
            result.append(line)
            continue

        if stripped.startswith(fence_char):
            remainder = stripped[len(fence_char):]
            if not remainder or remainder.strip() == "":
                in_fence = False
                strip_leading_blank = False
                fence_char = ""
                result.append(line)
                continue

        if strip_leading_blank and not stripped:
            continue

        strip_leading_blank = False
        result.append(line)

    return "\n".join(result)


def remove_orphan_output_headers(content: str) -> str:
    """Remove **Output** headers that are followed only by empty code blocks."""
    lines = content.splitlines()
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if line == "**Output**":
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines) and lines[j].startswith("```"):
                k = j + 1
                block_content: list[str] = []
                while k < len(lines):
                    if lines[k].startswith("```"):
                        break
                    block_content.append(lines[k])
                    k += 1

                non_empty = [entry for entry in block_content if entry.strip()]
                is_trivial = (
                    len(non_empty) == 0
                    or (len(non_empty) == 1 and non_empty[0].startswith("# [Included file not found"))
                )
                if is_trivial:
                    i = k + 1
                    continue

        result.append(line)
        i += 1

    return "\n".join(result)


def generate_skill_index(output_dir: Path) -> None:
    """Copy the static SKILL.md into the generated skill."""
    skill_path = output_dir / "SKILL.md"
    static_skill = Path(__file__).parent.resolve() / "BRAHE_SKILL.md"

    if not static_skill.exists():
        raise FileNotFoundError(f"Static SKILL.md not found: {static_skill}")

    shutil.copy2(static_skill, skill_path)


def parse_snippet_spec(spec: str) -> tuple[str, int | None, int | None]:
    """Parse a mkdocs include spec into a file path and optional line slice."""
    file_path, *line_parts = spec.split(":")
    start_line = int(line_parts[0]) if len(line_parts) >= 1 and line_parts[0].isdigit() else None
    end_line = int(line_parts[1]) if len(line_parts) >= 2 and line_parts[1].isdigit() else None
    return file_path, start_line, end_line


def dedent_lines(lines: list[str]) -> list[str]:
    """Remove the common indentation from a block of lines."""
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return lines

    min_indent = min(len(line) - len(line.lstrip()) for line in non_empty)
    return [strip_common_indent(line, min_indent) for line in lines]


def strip_common_indent(line: str, indent: int) -> str:
    """Strip a known indentation width without producing negative slices."""
    line_indent = len(line) - len(line.lstrip())
    if line_indent < indent:
        return line.lstrip()
    return line[indent:]


def resolve_repo_relative_path(repo_root: Path, raw_path: str) -> Path:
    """Resolve a repo-root-relative file reference used in mkdocs includes."""
    return (repo_root / raw_path.strip()).resolve()


def is_external_target(target: str) -> bool:
    """Return whether a markdown target points outside the local docs tree."""
    return target.startswith(("#", "/")) or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) is not None


def split_link_suffix(target: str) -> str:
    """Return the path portion of a markdown target, without query or fragment."""
    return re.split(r"[?#]", target, maxsplit=1)[0]


if __name__ == "__main__":
    sys.exit(main())
