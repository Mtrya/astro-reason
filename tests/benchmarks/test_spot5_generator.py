from pathlib import Path

from benchmarks.spot5.generator import (
    build_case_dataset,
    build_local_directory_provenance,
    collect_spot_files,
)


PROJECT_ROOT = Path(__file__).parent.parent.parent
CANONICAL_CASES_DIR = PROJECT_ROOT / "benchmarks" / "spot5" / "dataset" / "cases"


def test_build_case_dataset_from_local_source_dir(tmp_path):
    source_dir = tmp_path / "raw"
    source_dir.mkdir()

    for case_id in ("8", "1502"):
        source_path = CANONICAL_CASES_DIR / case_id / f"{case_id}.spot"
        (source_dir / f"{case_id}.spot").write_text(source_path.read_text())

    output_dir = tmp_path / "output"
    build_case_dataset(
        spot_files=collect_spot_files(source_dir),
        output_dir=output_dir,
        provenance=build_local_directory_provenance(source_dir),
    )

    index_path = output_dir / "index.json"
    assert index_path.exists()

    index = index_path.read_text()
    assert '"benchmark": "spot5"' in index
    assert '"case_id": "8"' in index
    assert '"case_id": "1502"' in index
    assert '"kind": "local_directory"' in index

    assert (output_dir / "cases" / "8" / "8.spot").read_text() == (
        source_dir / "8.spot"
    ).read_text()
    assert (output_dir / "cases" / "1502" / "1502.spot").read_text() == (
        source_dir / "1502.spot"
    ).read_text()
