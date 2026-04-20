from __future__ import annotations

from pathlib import Path

from scripts.generate_brahe_skill import (
    clean_mkdown_syntax,
    filter_tabs,
    normalize_fenced_code_blocks,
    process_docs_learn,
    remove_leading_blank_lines_in_fences,
)


def test_process_docs_learn_preserves_docs_tree_and_copies_reachable_docs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    docs_learn = repo_root / "docs" / "learn"
    source_file = docs_learn / "access_computation" / "index.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "\n".join(
            [
                "[Example](../../examples/ground_contacts.md)",
                "[API](../../library_api/access/index.md)",
                "![Figure](../../figures/coverage.png)",
                "",
                '```python',
                '--8<-- "./examples/access/demo.py"',
                '```',
            ]
        ),
        encoding="utf-8",
    )

    example_doc = repo_root / "docs" / "examples" / "ground_contacts.md"
    example_doc.parent.mkdir(parents=True)
    example_doc.write_text("# Example\n", encoding="utf-8")

    api_doc = repo_root / "docs" / "library_api" / "access" / "index.md"
    api_doc.parent.mkdir(parents=True)
    api_doc.write_text("# API\n", encoding="utf-8")

    figure = repo_root / "docs" / "figures" / "coverage.png"
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"png")

    included_script = repo_root / "examples" / "access" / "demo.py"
    included_script.parent.mkdir(parents=True)
    included_script.write_text("print('hello')\n", encoding="utf-8")

    out_root = tmp_path / "out"
    process_docs_learn(docs_learn, out_root, repo_root)

    rendered = (out_root / "docs" / "learn" / "access_computation" / "index.md").read_text(encoding="utf-8")

    assert "[Example](../../examples/ground_contacts.md)" in rendered
    assert "[API](../../library_api/access/index.md)" in rendered
    assert "![Figure](../../figures/coverage.png)" in rendered
    assert "print('hello')" in rendered
    assert (out_root / "docs" / "examples" / "ground_contacts.md").exists()
    assert (out_root / "docs" / "library_api" / "access" / "index.md").exists()
    assert (out_root / "docs" / "figures" / "coverage.png").exists()
    assert (out_root / "examples" / "access" / "demo.py").exists()


def test_process_docs_learn_copies_plot_helpers_and_theme_when_referenced(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    docs_learn = repo_root / "docs" / "learn"
    source_file = docs_learn / "plots" / "index.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "\n".join(
            [
                "```python",
                '--8<-- "./plots/learn/plots/example_plot.py"',
                "```",
            ]
        ),
        encoding="utf-8",
    )

    plot_script = repo_root / "plots" / "learn" / "plots" / "example_plot.py"
    plot_script.parent.mkdir(parents=True)
    plot_script.write_text("from brahe_theme import save_themed_html\n", encoding="utf-8")

    theme_file = repo_root / "plots" / "brahe_theme.py"
    theme_file.write_text("THEME = 'ok'\n", encoding="utf-8")

    out_root = tmp_path / "out"
    process_docs_learn(docs_learn, out_root, repo_root)

    assert (out_root / "plots" / "learn" / "plots" / "example_plot.py").read_text(encoding="utf-8") == (
        "from brahe_theme import save_themed_html\n"
    )
    assert (out_root / "plots" / "brahe_theme.py").read_text(encoding="utf-8") == "THEME = 'ok'\n"


def test_filter_tabs_keeps_following_content_after_tab_block() -> None:
    content = "\n".join(
        [
            '=== "Python"',
            "    ```python",
            '        print("hello")',
            "    ```",
            "",
            "After tabs",
        ]
    )

    assert filter_tabs(content) == "\n".join(
        [
            "```python",
            '    print("hello")',
            "```",
            "",
            "After tabs",
        ]
    )


def test_clean_mkdown_syntax_keeps_following_content_after_admonition() -> None:
    content = '\n'.join(['!!! note "Heads up"', "    Important detail", "", "After note"])

    assert clean_mkdown_syntax(content) == "\n".join(
        [
            "**Heads up**",
            "Important detail",
            "",
            "After note",
        ]
    )


def test_remove_leading_blank_lines_in_fences_strips_only_prefix_blank_lines() -> None:
    content = "\n".join(["```python", "", "", "print('hello')", "", "```"])

    assert remove_leading_blank_lines_in_fences(content) == "\n".join(
        ["```python", "print('hello')", "", "```"]
    )


def test_normalize_fenced_code_blocks_preserves_spaced_language_identifier() -> None:
    content = "\n".join(
        [
            "    ``` python",
            "    import brahe as bh",
            "    ```",
        ]
    )

    assert normalize_fenced_code_blocks(content) == "\n".join(
        [
            "```python",
            "import brahe as bh",
            "```",
        ]
    )
