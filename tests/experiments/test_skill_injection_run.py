from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.skill_injection import run


def test_default_config_builds_stereo_skill_injection_matrix() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
        benchmarks=("stereo_imaging",),
        conditions=(),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )

    assert [(item.condition, item.harness, item.case_id) for item in items] == [
        ("compact_domain", "opencode_dpsk", "case_0001"),
        ("skill_pack", "opencode_dpsk", "case_0001"),
    ]
    assert items[0].benchmark == "stereo_imaging"
    assert any(
        spec.target.as_posix().endswith("/skills/stereo-imaging-compact-procedure")
        for spec in items[0].assemble
    )


def test_skill_pack_condition_assembles_four_skill_sources() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    (item,) = run.build_items(
        config,
        benchmarks=("stereo_imaging",),
        conditions=("skill_pack",),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )
    specs = [
        spec
        for spec in item.assemble
        if "experiments/_fragments/skills/skill_injection" in spec.source.as_posix()
    ]

    assert [spec.target.name for spec in specs] == [
        "python-optimization-for-search",
        "classical-or-scheduling-methods",
        "ortools-cpsat-modeling",
        "stereo-imaging-product-strategy",
    ]


def test_compact_domain_selects_benchmark_specific_skill_sources() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
        benchmarks=("stereo_imaging", "regional_coverage", "relay_constellation"),
        conditions=("compact_domain",),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )
    skills_by_benchmark = {
        item.benchmark: [
            spec.target.name
            for spec in item.assemble
            if "experiments/_fragments/skills/skill_injection" in spec.source.as_posix()
        ]
        for item in items
    }

    assert skills_by_benchmark == {
        "stereo_imaging": ["stereo-imaging-compact-procedure"],
        "regional_coverage": ["regional-coverage-compact-procedure"],
        "relay_constellation": ["relay-constellation-compact-procedure"],
    }


def test_skill_pack_selects_benchmark_specific_strategy_sources() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
        benchmarks=("stereo_imaging", "regional_coverage", "relay_constellation"),
        conditions=("skill_pack",),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )
    skills_by_benchmark = {
        item.benchmark: [
            spec.target.name
            for spec in item.assemble
            if "experiments/_fragments/skills/skill_injection" in spec.source.as_posix()
        ]
        for item in items
    }

    assert skills_by_benchmark == {
        "stereo_imaging": [
            "python-optimization-for-search",
            "classical-or-scheduling-methods",
            "ortools-cpsat-modeling",
            "stereo-imaging-product-strategy",
        ],
        "regional_coverage": [
            "python-optimization-for-search",
            "classical-or-scheduling-methods",
            "ortools-cpsat-modeling",
            "regional-coverage-strip-strategy",
        ],
        "relay_constellation": [
            "python-optimization-for-search",
            "classical-or-scheduling-methods",
            "relay-constellation-service-strategy",
        ],
    }


def test_regional_and_relay_filters_expand_to_40_skill_runs() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
        benchmarks=("regional_coverage", "relay_constellation"),
        conditions=("compact_domain", "skill_pack"),
        harnesses=("opencode_dpsk", "opencode_minimax"),
        cases=("case_0001", "case_0002", "case_0003", "case_0004", "case_0005"),
    )

    assert len(items) == 40
    for item in items:
        skill_names = [
            spec.target.name
            for spec in item.assemble
            if "experiments/_fragments/skills/skill_injection" in spec.source.as_posix()
        ]
        if item.benchmark == "regional_coverage":
            assert any(name.startswith("regional-coverage-") for name in skill_names)
            assert not any(name.startswith("relay-constellation-") for name in skill_names)
        if item.benchmark == "relay_constellation":
            assert any(name.startswith("relay-constellation-") for name in skill_names)
            assert not any(name.startswith("regional-coverage-") for name in skill_names)


def test_interactive_dry_run_selects_stereo_skill_condition(capsys) -> None:
    assert run.main(
        [
            "--interactive",
            "--dry-run",
            "--benchmark",
            "stereo_imaging",
            "--condition",
            "compact_domain",
            "--harness",
            "opencode_dpsk",
            "--case",
            "case_0001",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Interactive benchmark: stereo_imaging" in output
    assert "Interactive condition: compact_domain" in output
    assert "Interactive harness: opencode_dpsk" in output
    assert "Missing assemble sources: none" in output


def test_missing_assemble_sources_report_skill_directories_only_for_skill_conditions() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
        benchmarks=("stereo_imaging",),
        conditions=("compact_domain", "skill_pack"),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )

    missing_by_condition = {
        item.condition: [spec.source for spec in run.missing_assemble_sources(item)]
        for item in items
    }

    assert [
        path.name
        for path in missing_by_condition["skill_pack"]
        if "experiments/_fragments/skills/skill_injection" in path.as_posix()
    ] == []
    assert [
        path.name
        for path in missing_by_condition["compact_domain"]
        if "experiments/_fragments/skills/skill_injection" in path.as_posix()
    ] == []


def test_skill_fragment_root_contains_only_skill_directories() -> None:
    skill_root = REPO_ROOT / "experiments" / "_fragments" / "skills" / "skill_injection"

    assert sorted(path.name for path in skill_root.iterdir()) == [
        "classical-or-scheduling-methods",
        "ortools-cpsat-modeling",
        "python-optimization-for-search",
        "regional-coverage-compact-procedure",
        "regional-coverage-strip-strategy",
        "relay-constellation-compact-procedure",
        "relay-constellation-service-strategy",
        "stereo-imaging-compact-procedure",
        "stereo-imaging-product-strategy",
    ]
    assert all(path.is_dir() for path in skill_root.iterdir())
