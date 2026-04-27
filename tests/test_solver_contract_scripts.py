from __future__ import annotations

import stat
import sys
from pathlib import Path

from scripts import validate_solver_contract as solver_contract


def test_run_command_reports_launch_errors(tmp_path: Path) -> None:
    returncode, launch_error = solver_contract._run_command(
        ["./missing.sh"],
        cwd=tmp_path,
    )

    assert returncode is None
    assert launch_error is not None
    assert "missing.sh" in launch_error


def test_run_command_reports_timeouts(tmp_path: Path) -> None:
    returncode, launch_error = solver_contract._run_command(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        cwd=tmp_path,
        timeout_s=0.01,
    )

    assert returncode == 124
    assert launch_error is not None
    assert "timed out" in launch_error


def test_boundary_scan_skips_generated_solver_dirs(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    solver_root = repo_root / "solvers" / "demo_benchmark" / "demo_solver"
    generated = solver_root / ".venv" / "lib"
    source = solver_root / "src"
    generated.mkdir(parents=True)
    source.mkdir(parents=True)
    (generated / "third_party.py").write_text("import benchmarks\n", encoding="utf-8")
    (source / "solver.py").write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setattr(solver_contract, "REPO_ROOT", repo_root)

    files = {path.relative_to(repo_root).as_posix() for path in solver_contract._iter_solver_runtime_files()}

    assert "solvers/demo_benchmark/demo_solver/src/solver.py" in files
    assert "solvers/demo_benchmark/demo_solver/.venv/lib/third_party.py" not in files


def test_pytest_boundary_rejects_solver_path_prefix(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\ntestpaths = tests solvers/foo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(solver_contract, "REPO_ROOT", tmp_path)

    errors: list[str] = []
    solver_contract._validate_pytest_boundary(errors)

    assert "pytest.ini testpaths must not include solvers/" in errors


def test_non_executable_test_sh_is_reported_without_traceback(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    solver_dir = repo_root / "solvers" / "demo_benchmark" / "demo_solver"
    solver_dir.mkdir(parents=True)
    test_script = solver_dir / "test.sh"
    test_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    test_script.chmod(stat.S_IRUSR | stat.S_IWUSR)

    monkeypatch.setattr(solver_contract, "REPO_ROOT", repo_root)

    errors: list[str] = []
    solver_contract._run_solver_tests(
        [{"benchmark": "demo_benchmark", "solver": "demo_solver"}],
        errors,
    )

    assert errors
    assert "could not complete" in errors[0]


def test_solver_tests_run_setup_first(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    solver_dir = repo_root / "solvers" / "demo_benchmark" / "demo_solver"
    solver_dir.mkdir(parents=True)
    setup_script = solver_dir / "setup.sh"
    test_script = solver_dir / "test.sh"
    marker = solver_dir / "setup.marker"
    setup_script.write_text("#!/usr/bin/env bash\ntouch setup.marker\n", encoding="utf-8")
    test_script.write_text(
        "#!/usr/bin/env bash\n"
        "test -f setup.marker\n",
        encoding="utf-8",
    )
    setup_script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    test_script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    monkeypatch.setattr(solver_contract, "REPO_ROOT", repo_root)

    errors: list[str] = []
    solver_contract._run_solver_tests(
        [{"benchmark": "demo_benchmark", "solver": "demo_solver"}],
        errors,
    )

    assert errors == []
    assert marker.exists()
