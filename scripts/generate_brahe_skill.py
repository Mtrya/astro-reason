#!/usr/bin/env python3
"""Generate the Brahe skill from upstream docs and examples.

Reads from vendor/brahe/ (or clones upstream) and writes processed
artifacts to .agent/skills/brahe/.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Brahe skill")
    parser.add_argument(
        "--source",
        default=None,
        help="Path to Brahe source directory (defaults to cloning from GitHub)",
    )
    parser.add_argument(
        "--output",
        default=".agent/skills/brahe",
        help="Output directory for the skill",
    )
    args = parser.parse_args()

    output = Path(args.output).resolve()

    temp_dir = None
    source = None
    try:
        if args.source is None:
            temp_dir = tempfile.TemporaryDirectory(prefix="brahe-skill-source-")
            source = Path(temp_dir.name) / "brahe"
            print("Cloning Brahe from GitHub ...")
            subprocess.run(
                [
                    "git", "clone", "--depth", "1",
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

        # Safety guard for output deletion
        if output.exists():
            resolved_out = output.resolve()
            dangerous = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
            if resolved_out in dangerous:
                print(f"Refusing to delete protected directory: {output}", file=sys.stderr)
                return 1
            shutil.rmtree(output)
        output.mkdir(parents=True)

        # Create subdirectories
        (output / "scripts").mkdir()
        (output / "references").mkdir()
        (output / "assets" / "figures").mkdir(parents=True)
        (output / "assets" / "docs_assets").mkdir(parents=True)

        # 1. Process docs/learn/ markdown files
        docs_learn = source / "docs" / "learn"
        if docs_learn.exists():
            process_docs_learn(docs_learn, output / "references", source)

        # 2. Copy examples/ Python files
        examples_dir = source / "examples"
        if examples_dir.exists():
            process_examples(examples_dir, output / "scripts")

        # 3. Copy assets and figures
        docs_figures = source / "docs" / "figures"
        docs_assets = source / "docs" / "assets"
        if docs_figures.exists():
            copy_tree(docs_figures, output / "assets" / "figures")
        if docs_assets.exists():
            copy_tree(docs_assets, output / "assets" / "docs_assets")

        # 4. Generate SKILL.md
        generate_skill_index(output, source)

    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    print(f"Skill generated at: {output}")
    return 0


def process_docs_learn(src_dir: Path, out_dir: Path, repo_root: Path) -> None:
    """Copy and transform docs/learn/ markdown files."""
    for src_file in sorted(src_dir.rglob("*.md")):
        rel = src_file.relative_to(src_dir)
        out_file = out_dir / rel
        out_file.parent.mkdir(parents=True, exist_ok=True)

        content = src_file.read_text(encoding="utf-8")
        content = resolve_snippets(content, repo_root)
        content = filter_tabs(content)
        content = rewrite_relative_links(content)
        content = clean_mkdown_syntax(content)
        content = normalize_fenced_code_blocks(content)
        content = remove_orphan_output_headers(content)

        out_file.write_text(content, encoding="utf-8")


def resolve_snippets(content: str, repo_root: Path) -> str:
    """Replace --8<-- includes with inlined file contents.

    Handles lines like:
        --8<-- "./examples/foo.py:8"
        --8<-- "./examples/foo.py:8:20"
    even when indented inside fenced code blocks.
    """
    pattern = re.compile(r"^(\s*)--8<--\s+['\"](.+?)['\"]\s*$", re.MULTILINE)

    def replacer(match: re.Match) -> str:
        indent = match.group(1)
        spec = match.group(2)
        parts = spec.split(":")
        file_path = parts[0]
        start_line = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        end_line = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

        # Skip build-artifact output files that only exist after mkdocs build
        normalized = file_path.lstrip("./")
        if normalized.startswith("docs/outputs/"):
            return ""

        target = repo_root / file_path
        if not target.exists():
            return f"{indent}# [Included file not found: {file_path}]"

        lines = target.read_text(encoding="utf-8").splitlines()
        if start_line is not None:
            start_idx = start_line - 1
            end_idx = end_line if end_line is not None else len(lines)
            lines = lines[start_idx:end_idx]

        if lines:
            non_empty = [line for line in lines if line.strip()]
            if non_empty:
                min_indent = min((len(line) - len(line.lstrip())) for line in non_empty)
                stripped = [line[min_indent:] for line in lines]
            else:
                stripped = lines
            indented = [indent + line for line in stripped]
            return "\n".join(indented)
        return ""

    return pattern.sub(replacer, content)


def filter_tabs(content: str) -> str:
    """Remove pymdownx.tabbed Rust blocks, keep Python blocks.

    pymdownx.tabbed uses:
    === "Python"
        content...
    === "Rust"
        content...

    We keep Python content and drop Rust content entirely. Content inside kept
    tabs is dedented so fenced code blocks and prose render correctly.
    """
    lines = content.splitlines()
    result: list[str] = []
    skip_until_dedent = False
    in_python_tab = False
    tab_base_indent = 0
    python_tab_dedent: int | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        tab_match = re.match(r'^(===)\s+["\'](.+?)["\']\s*$', stripped)
        if tab_match:
            tab_name = tab_match.group(2)
            if tab_name == "Rust":
                skip_until_dedent = True
                in_python_tab = False
                tab_base_indent = indent
                i += 1
                continue
            elif tab_name == "Python":
                in_python_tab = True
                skip_until_dedent = False
                tab_base_indent = indent
                python_tab_dedent = None
                i += 1
                continue
            else:
                skip_until_dedent = False
                in_python_tab = False
                result.append(line)
                i += 1
                continue

        if skip_until_dedent:
            if stripped and indent <= tab_base_indent:
                skip_until_dedent = False
                continue
            continue

        if in_python_tab:
            if stripped and indent <= tab_base_indent:
                in_python_tab = False
                continue
                continue

            if not stripped:
                result.append("")
                i += 1
                continue

            if python_tab_dedent is None:
                python_tab_dedent = indent

            dedented = line[python_tab_dedent:] if indent >= python_tab_dedent else line.lstrip()
            result.append(dedented)
            i += 1
            continue

        result.append(line)
        i += 1

    return "\n".join(result)


def rewrite_relative_links(content: str) -> str:
    """Rewrite relative markdown links to point to Brahe's published docs."""
    base_url = "https://duncaneddy.github.io/brahe/latest"

    def replacer(match: re.Match) -> str:
        text = match.group(1)
        link = match.group(2)
        if link.startswith("http") or link.startswith("#"):
            return match.group(0)

        # Normalize relative path
        link_clean = link
        for prefix in ("../../", "../", "./"):
            if link_clean.startswith(prefix):
                link_clean = link_clean[len(prefix):]
        link_clean = link_clean.replace(".md", "")
        return f"[{text}]({base_url}/{link_clean})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replacer, content)


def clean_mkdown_syntax(content: str) -> str:
    """Remove or simplify mkdocs-material specific syntax.

    - !!! admonitions -> bold header + dedented content
    - ??? collapsible blocks -> bold header + dedented content
    - HTML divs for plotly embeds -> removed
    - HTML figure tags -> removed
    - HTML center-table div tags -> removed, content kept
    """
    lines = content.splitlines()
    result: list[str] = []
    plotly_depth = 0
    in_center_table = False
    in_special = False
    special_base_indent = 0
    special_dedent: int | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # HTML divs and figures
        if stripped.startswith("<div"):
            if 'class="plotly-embed"' in stripped:
                plotly_depth += 1
                i += 1
                continue
            elif 'class="center-table"' in stripped:
                in_center_table = True
                i += 1
                continue
        elif stripped.startswith("</div>"):
            if plotly_depth > 0:
                plotly_depth -= 1
                i += 1
                continue
            elif in_center_table:
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

        # Admonitions and details
        special_match = re.match(r"^(!!!|\?\?\?)\s+(\w+)?\s*(\"?(.+?)\"?)?\s*$", stripped)
        if special_match:
            in_special = True
            special_base_indent = indent
            special_dedent = None
            title = special_match.group(4) or special_match.group(2) or "Note"
            result.append(f"**{title}**")
            i += 1
            continue

        if in_special:
            if not stripped:
                result.append("")
                i += 1
                continue
            if indent <= special_base_indent:
                in_special = False
                result.append(line)
                i += 1
                continue

            if special_dedent is None:
                special_dedent = indent

            dedented = line[special_dedent:] if indent >= special_dedent else line.lstrip()
            result.append(dedented)
            i += 1
            continue

        result.append(line)
        i += 1

    return "\n".join(result)


def normalize_fenced_code_blocks(content: str) -> str:
    """Dedent indented fenced code blocks so the fence starts at column 0.

    After filter_tabs removes === "Python" headers, code blocks often retain
    their original indentation (e.g., 4 spaces). This function normalizes them.
    """
    lines = content.splitlines()
    result: list[str] = []
    in_fence = False
    fence_indent = 0
    fence_char = ""

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if not in_fence:
            # Detect fence opener: optional indent, then ``` or ~~~, optional info
            m = re.match(r"^(\s*)(`{3,}|~{3,})\s*(\S*).*", stripped)
            if m:
                in_fence = True
                fence_indent = indent
                fence_char = m.group(2)
                info = m.group(3)
                if info:
                    result.append(f"{fence_char}{info}")
                else:
                    result.append(fence_char)
                continue
            result.append(line)
        else:
            # Check for fence closer
            if stripped.startswith(fence_char) and len(stripped) >= len(fence_char):
                # Make sure it's actually a closer, not just a line with backticks
                remainder = stripped[len(fence_char):]
                if not remainder or remainder.strip() == "":
                    in_fence = False
                    result.append(fence_char)
                    continue
            # Dedent content line by fence_indent, but not below 0
            if line.strip():
                dedented = line[fence_indent:] if indent >= fence_indent else line.lstrip()
            else:
                dedented = ""
            result.append(dedented)

    return "\n".join(result)


def remove_orphan_output_headers(content: str) -> str:
    """Remove **Output** headers that are followed only by empty code blocks.

    This happens when docs/outputs/ includes were skipped and only a bare
    ```\n# [Included file not found: ...]\n``` remains, or an empty block.
    """
    lines = content.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "**Output**":
            # Peek ahead: if the next non-empty lines form a trivial code block,
            # skip the header and the block.
            j = i + 1
            # Skip blank lines
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].startswith("```"):
                # Found a code block after **Output**
                k = j + 1
                block_content: list[str] = []
                while k < len(lines):
                    if lines[k].startswith("```"):
                        break
                    block_content.append(lines[k])
                    k += 1
                # Decide if the block is trivial
                non_empty = [l for l in block_content if l.strip()]
                is_trivial = (
                    len(non_empty) == 0
                    or (len(non_empty) == 1 and non_empty[0].startswith("# [Included file not found"))
                )
                if is_trivial:
                    # Skip past the closing fence
                    i = k + 1
                    continue
        result.append(line)
        i += 1

    return "\n".join(result)


def process_examples(src_dir: Path, out_dir: Path) -> None:
    """Copy Python example files, filtering out CI-only and ignored files."""
    for src_file in sorted(src_dir.rglob("*.py")):
        rel = src_file.relative_to(src_dir)
        out_file = out_dir / rel

        # Skip CI-only and ignored examples
        content = src_file.read_text(encoding="utf-8")
        if '# FLAGS = ["CI-ONLY"]' in content or '# FLAGS = ["IGNORE"]' in content:
            continue

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content, encoding="utf-8")


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree."""
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def generate_skill_index(output_dir: Path, source_dir: Path) -> None:
    """Copy the static SKILL.md into the generated skill.

    The canonical SKILL.md lives at scripts/BRAHE_SKILL.md so it can be reviewed
    and updated independently of the generator code.
    """
    skill_path = output_dir / "SKILL.md"
    script_dir = Path(__file__).parent.resolve()
    static_skill = script_dir / "BRAHE_SKILL.md"

    if not static_skill.exists():
        print(f"Static SKILL.md not found: {static_skill}", file=sys.stderr)
        return

    shutil.copy2(static_skill, skill_path)


if __name__ == "__main__":
    sys.exit(main())
