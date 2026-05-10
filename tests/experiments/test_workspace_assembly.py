from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import plan as main_plan
from experiments.main_agentic import run as main_run
from experiments.temporal_robustness import run as temporal_run
from experiments.verifier_exposure import run as verifier_run


def test_main_agentic_assemble_renders_and_records_missing_sources(tmp_path: Path) -> None:
    source = tmp_path / "README.template.md"
    source.write_text(
        "benchmark={benchmark} split={split} case={case_id} unknown={json_like}",
        encoding="utf-8",
    )
    roots = main_run.MountRoots(
        workspace=tmp_path / "workspace",
        home=tmp_path / "home",
        output=tmp_path / "output",
    )
    roots.workspace.mkdir()
    roots.home.mkdir()
    roots.output.mkdir()

    records = main_run._assemble_workspace(
        (
            main_plan.AssembleSpec(
                source=source,
                target=main_run.WORKSPACE_MOUNT / "README.md",
                render=True,
                missing_ok=False,
                example=None,
            ),
            main_plan.AssembleSpec(
                source=tmp_path / "optional.txt",
                target=main_run.WORKSPACE_MOUNT / "optional.txt",
                render=False,
                missing_ok=True,
                example=None,
            ),
        ),
        roots,
        benchmark="demo_benchmark",
        split="train",
        case_id="case_0007",
    )

    assert (roots.workspace / "README.md").read_text(encoding="utf-8") == (
        "benchmark=demo_benchmark split=train case=case_0007 unknown={json_like}"
    )
    assert records == [
        {
            "source": str(source),
            "target": "/app/workspace/README.md",
            "present": True,
            "rendered": True,
        },
        {
            "source": str(tmp_path / "optional.txt"),
            "target": "/app/workspace/optional.txt",
            "present": False,
            "rendered": False,
        },
    ]


def test_main_agentic_collect_copies_files_and_records_missing_optional_sources(
    tmp_path: Path,
) -> None:
    roots = main_run.MountRoots(
        workspace=tmp_path / "workspace",
        home=tmp_path / "home",
        output=tmp_path / "container_output",
    )
    roots.workspace.mkdir()
    roots.home.mkdir()
    roots.output.mkdir()
    (roots.output / "logs").mkdir()
    (roots.output / "logs" / "stdout.txt").write_text("hello\n", encoding="utf-8")
    output_dir = tmp_path / "run_output"

    records = main_run._collect_artifacts(
        (
            main_plan.CollectSpec(
                source=main_run.OUTPUT_MOUNT / "logs",
                target=Path("results_root/logs"),
                missing_ok=False,
            ),
            main_plan.CollectSpec(
                source=main_run.OUTPUT_MOUNT / "missing",
                target=Path("results_root/missing"),
                missing_ok=True,
            ),
        ),
        roots,
        output_dir,
    )

    assert (output_dir / "logs" / "stdout.txt").read_text(encoding="utf-8") == "hello\n"
    assert records == [
        {
            "source": "/app/run/output/logs",
            "target": "results_root/logs",
            "present": True,
        },
        {
            "source": "/app/run/output/missing",
            "target": "results_root/missing",
            "present": False,
        },
    ]


def test_ablation_source_available_treats_empty_directories_as_missing(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    nonempty_dir = tmp_path / "nonempty"
    nonempty_dir.mkdir()
    (nonempty_dir / "file.txt").write_text("x", encoding="utf-8")

    assert verifier_run._source_available(empty_dir) is False
    assert verifier_run._source_available(nonempty_dir) is True
    assert temporal_run._source_available(empty_dir) is False
    assert temporal_run._source_available(nonempty_dir) is True


def test_main_agentic_currently_allows_empty_assembled_directories(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty_source"
    empty_dir.mkdir()
    roots = main_run.MountRoots(
        workspace=tmp_path / "workspace",
        home=tmp_path / "home",
        output=tmp_path / "output",
    )
    roots.workspace.mkdir()
    roots.home.mkdir()
    roots.output.mkdir()

    records = main_run._assemble_workspace(
        (
            main_plan.AssembleSpec(
                source=empty_dir,
                target=main_run.WORKSPACE_MOUNT / "empty_target",
                render=False,
                missing_ok=False,
                example=None,
            ),
        ),
        roots,
        benchmark="demo_benchmark",
        split="test",
        case_id="case_0001",
    )

    assert (roots.workspace / "empty_target").is_dir()
    assert list((roots.workspace / "empty_target").iterdir()) == []
    assert records == [
        {
            "source": str(empty_dir),
            "target": "/app/workspace/empty_target",
            "present": True,
            "rendered": False,
        }
    ]
