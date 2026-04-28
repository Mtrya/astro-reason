from __future__ import annotations

import stat
import sys
import os
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


def test_solver_subprocess_env_scrubs_workspace_python_leakage(monkeypatch) -> None:
    repo_bin = solver_contract.REPO_ROOT / ".venv" / "bin"
    monkeypatch.setenv("PATH", f"{repo_bin}:/usr/local/bin:/usr/bin")
    monkeypatch.setenv("PYTHONPATH", str(solver_contract.REPO_ROOT))
    monkeypatch.setenv("PYTHONHOME", "/tmp/pythonhome")
    monkeypatch.setenv("PYTHONUSERBASE", "/tmp/pythonuserbase")
    monkeypatch.setenv("VIRTUAL_ENV", str(solver_contract.REPO_ROOT / ".venv"))
    monkeypatch.setenv("UV_CACHE_DIR", "/tmp/repo-uv-cache")
    monkeypatch.setenv("UV_DEFAULT_INDEX", "https://mirror.example/simple")
    monkeypatch.setenv("UV_EXTRA_INDEX_URL", "https://extra.example/simple")
    monkeypatch.setenv("UV_INDEX_URL", "https://legacy.example/simple")
    monkeypatch.setenv("UV_INDEX_PRIVATE_USERNAME", "ci-user")
    monkeypatch.setenv("UV_INDEX_PRIVATE_PASSWORD", "ci-pass")
    monkeypatch.setenv("UV_KEYRING_PROVIDER", "subprocess")
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "/tmp/uv-python-dir")
    monkeypatch.setenv("UV_PROJECT", str(solver_contract.REPO_ROOT))
    monkeypatch.setenv("UV_WORKING_DIR", str(solver_contract.REPO_ROOT))
    monkeypatch.setenv("SOLVER_PYTHON", "/tmp/solver-python")

    env = solver_contract._solver_subprocess_env()

    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert "PYTHONUSERBASE" not in env
    assert "VIRTUAL_ENV" not in env
    assert "UV_PROJECT" not in env
    assert "UV_WORKING_DIR" not in env
    assert env["UV_CACHE_DIR"] == "/tmp/repo-uv-cache"
    assert env["UV_DEFAULT_INDEX"] == "https://mirror.example/simple"
    assert env["UV_EXTRA_INDEX_URL"] == "https://extra.example/simple"
    assert env["UV_INDEX_URL"] == "https://legacy.example/simple"
    assert env["UV_INDEX_PRIVATE_USERNAME"] == "ci-user"
    assert env["UV_INDEX_PRIVATE_PASSWORD"] == "ci-pass"
    assert env["UV_KEYRING_PROVIDER"] == "subprocess"
    assert env["UV_PYTHON_INSTALL_DIR"] == "/tmp/uv-python-dir"
    assert str(repo_bin) not in env["PATH"].split(":")
    assert env["SOLVER_PYTHON"] == "/tmp/solver-python"
    assert env["UV_NO_PROJECT"] == "1"
    assert env["UV_NO_CONFIG"] == "1"


def test_run_command_uses_explicit_environment(tmp_path: Path) -> None:
    script = tmp_path / "check_env.py"
    marker = tmp_path / "marker"
    script.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['MARKER']).write_text(os.environ.get('PYTHONPATH', ''), encoding='utf-8')\n",
        encoding="utf-8",
    )

    returncode, launch_error = solver_contract._run_command(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", ""), "MARKER": str(marker)},
    )

    assert returncode == 0
    assert launch_error is None
    assert marker.read_text(encoding="utf-8") == ""


def test_entrypoint_isolation_rejects_uv_run(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    solver_dir = repo_root / "solvers" / "demo_benchmark" / "demo_solver"
    solver_dir.mkdir(parents=True)
    (solver_dir / "test.sh").write_text(
        "#!/usr/bin/env bash\nuv run pytest tests\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(solver_contract, "REPO_ROOT", repo_root)

    errors: list[str] = []
    solver_contract._validate_entrypoint_isolation(
        [{"benchmark": "demo_benchmark", "solver": "demo_solver"}],
        errors,
    )

    assert errors
    assert "test.sh uses 'uv run'" in errors[0]
    assert "solver-local environment" in errors[0]


def test_setup_scripts_do_not_install_into_external_solver_python() -> None:
    setup_scripts = [
        solver_contract.REPO_ROOT / "solvers" / "aeossp_standard" / "greedy_lns" / "setup.sh",
        solver_contract.REPO_ROOT / "solvers" / "aeossp_standard" / "mwis_conflict_graph" / "setup.sh",
        solver_contract.REPO_ROOT / "solvers" / "regional_coverage" / "celf_submodular" / "setup.sh",
        solver_contract.REPO_ROOT / "solvers" / "relay_constellation" / "mclp_teg_contact_plan" / "setup.sh",
        solver_contract.REPO_ROOT / "solvers" / "revisit_constellation" / "rgt_apc_gap_constructive" / "setup.sh",
        solver_contract.REPO_ROOT / "solvers" / "stereo_imaging" / "cp_local_search_stereo_insertion" / "setup.sh",
    ]
    for script in setup_scripts:
        text = script.read_text(encoding="utf-8")
        assert 'PYTHON_BIN="${VENV_DIR}/bin/python"' in text
        assert "SOLVER_PYTHON:-" not in text
        assert "python3.13 -m venv" in text
        assert "python3 -m venv" not in text


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
