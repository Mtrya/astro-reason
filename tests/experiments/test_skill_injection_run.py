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
        "ortools-cpsat-modeling",
        "classical-or-scheduling-methods",
        "stereo-imaging-product-strategy",
    ]


def test_missing_assemble_sources_report_skill_directories_only_for_skill_conditions() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
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
        "stereo-imaging-compact-procedure",
        "stereo-imaging-product-strategy",
    ]
    assert all(path.is_dir() for path in skill_root.iterdir())
