import io
import sys
import zipfile
from pathlib import Path

import benchmarks.spot5.generator as generator_module
from benchmarks.spot5.generator import (
    build_case_dataset,
    build_local_directory_provenance,
    collect_spot_files,
    download_upstream_zip,
    DOWNLOAD_USER_AGENT,
    extract_zip_tree,
)


PROJECT_ROOT = Path(__file__).parent.parent.parent


def test_build_case_dataset_from_local_source_dir(tmp_path):
    source_dir = tmp_path / "raw"
    source_dir.mkdir()

    (source_dir / "8.spot").write_text("8\n0\n")
    (source_dir / "1502.spot").write_text("1502\n0\n")

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

    assert (output_dir / "cases" / "8" / "8.spot").read_text() == "8\n0\n"
    assert (output_dir / "cases" / "1502" / "1502.spot").read_text() == "1502\n0\n"


def test_download_upstream_zip_uses_explicit_user_agent(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request):
        captured["full_url"] = request.full_url
        captured["user_agent"] = request.get_header("User-agent")
        return FakeResponse(b"PK\x03\x04fake-zip")

    monkeypatch.setattr(generator_module, "urlopen", fake_urlopen)

    destination = tmp_path / "spot5.zip"
    result = download_upstream_zip(destination)

    assert result == destination
    assert destination.read_bytes() == b"PK\x03\x04fake-zip"
    assert captured["full_url"] == generator_module.UPSTREAM_DATASET_URL
    assert captured["user_agent"] == DOWNLOAD_USER_AGENT


def test_extract_zip_tree_extracts_nested_zip_contents(tmp_path):
    inner_zip = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner_zip, "w") as archive:
        archive.writestr("8.spot", "8\n0\n")

    outer_zip = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_zip, "w") as archive:
        archive.write(inner_zip, arcname="wrapper/spot5.zip")

    extract_dir = tmp_path / "extracted"
    extract_zip_tree(outer_zip, extract_dir)

    extracted_spot = extract_dir / "wrapper" / "spot5" / "8.spot"
    assert extracted_spot.exists()
    assert extracted_spot.read_text() == "8\n0\n"


def test_main_builds_dataset_from_local_nested_zip(monkeypatch, tmp_path):
    inner_zip = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner_zip, "w") as archive:
        archive.writestr("SPOT5 benchmarks/8.spot", "8\n0\n")

    outer_zip = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_zip, "w") as archive:
        archive.write(
            inner_zip,
            arcname="Benckmark inctances of the (SPOT5) daily photograph scheduling problem/SPOT5 benchmarks.zip",
        )

    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generator.py",
            "--zip-path",
            str(outer_zip),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert generator_module.main() == 0
    assert (output_dir / "cases" / "8" / "8.spot").read_text() == "8\n0\n"
