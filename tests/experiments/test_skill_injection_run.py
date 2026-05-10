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
        conditions=("no_skill", "compact_domain"),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )

    assert [(item.condition, item.harness, item.case_id) for item in items] == [
        ("no_skill", "opencode_dpsk", "case_0001"),
        ("compact_domain", "opencode_dpsk", "case_0001"),
    ]
    assert items[0].benchmark == "stereo_imaging"
    assert not any("skill_injection" in spec.source.as_posix() for spec in items[0].assemble)
    assert any(
        spec.target.as_posix().endswith("/skills/stereo-imaging-compact-procedure")
        for spec in items[1].assemble
    )


def test_skill_pack_expands_to_four_planned_skill_sources() -> None:
    harness = run.load_harness_profile("opencode_dpsk")
    bundle = run.load_skill_bundle("skill_pack", harness)

    assert bundle.status == "planned"
    assert [spec.target.name for spec in bundle.skills] == [
        "python-optimization-for-search",
        "ortools-cpsat-modeling",
        "classical-or-scheduling-methods",
        "stereo-imaging-product-strategy",
    ]


def test_missing_assemble_sources_report_planned_skill_directories_only_for_skill_conditions() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    items = run.build_items(
        config,
        conditions=("no_skill", "skill_pack"),
        harnesses=("opencode_dpsk",),
        cases=("case_0001",),
    )

    missing_by_condition = {
        item.condition: [spec.source for spec in run.missing_assemble_sources(item)]
        for item in items
    }

    assert not any("skill_injection" in path.as_posix() for path in missing_by_condition["no_skill"])
    assert [
        path.name
        for path in missing_by_condition["skill_pack"]
        if "experiments/_fragments/skills/skill_injection" in path.as_posix()
    ] == [
        "stereo-imaging-product-strategy",
    ]
