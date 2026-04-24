"""Focused tests for relay_constellation UMCF/SRR solver candidate generation and dynamic graphs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.relay_constellation.umcf_srr_contact_plan.src.case_io import (
    Case,
    Demand,
    Endpoint,
    Manifest,
    Satellite,
    load_case,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.time_grid import (
    all_sample_times,
    demand_indices,
    interval_indices,
    sample_index,
    time_for_index,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.orbit_library import (
    CandidateConfig,
    _orbit_summary,
    generate_candidates,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.dynamic_graph import (
    SampleGraph,
    build_sample_graphs,
    graph_summary,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.solution_io import (
    write_solution,
    write_status,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.candidate_selection import (
    SelectionConfig,
    _evaluate_allowed_set,
    _evaluate_sample,
    select_candidates,
)
from solvers.relay_constellation.umcf_srr_contact_plan.src.solve import solve


def _smoke_case_dir() -> Path:
    return REPO_ROOT / "benchmarks" / "relay_constellation" / "dataset" / "cases" / "test" / "case_0001"


class TestCaseIO:
    def test_load_smoke_case(self) -> None:
        case = load_case(_smoke_case_dir())
        assert case.manifest.case_id == "case_0001"
        assert len(case.backbone_satellites) > 0
        assert len(case.ground_endpoints) > 0
        assert len(case.demands) > 0
        assert case.manifest.total_samples > 0

    def test_manifest_constraints_present(self) -> None:
        case = load_case(_smoke_case_dir())
        assert case.manifest.max_added_satellites > 0
        assert case.manifest.min_altitude_m < case.manifest.max_altitude_m
        assert case.manifest.max_isl_range_m > 0


class TestTimeGrid:
    def test_sample_index_round_trip(self) -> None:
        case = load_case(_smoke_case_dir())
        manifest = case.manifest
        for idx in [0, 1, manifest.total_samples - 1]:
            t = time_for_index(manifest, idx)
            assert sample_index(manifest, t) == idx

    def test_all_sample_times_count(self) -> None:
        case = load_case(_smoke_case_dir())
        times = all_sample_times(case.manifest)
        assert len(times) == case.manifest.total_samples

    def test_demand_indices_non_empty(self) -> None:
        case = load_case(_smoke_case_dir())
        for demand in case.demands:
            indices = demand_indices(case.manifest, demand)
            assert len(indices) > 0


class TestOrbitLibrary:
    def test_generate_candidates_respects_constraints(self) -> None:
        case = load_case(_smoke_case_dir())
        manifest = case.manifest
        candidates = generate_candidates(manifest)
        assert len(candidates) <= 16
        for sat in candidates.values():
            summary = _orbit_summary(sat.state_eci_m_mps)
            assert summary["perigee_altitude_m"] >= manifest.min_altitude_m - 1e-9
            assert summary["apogee_altitude_m"] <= manifest.max_altitude_m + 1e-9
            if manifest.max_eccentricity is not None:
                assert summary["eccentricity"] <= manifest.max_eccentricity + 1e-9
            if manifest.min_inclination_deg is not None:
                assert summary["inclination_deg"] >= manifest.min_inclination_deg - 1e-9
            if manifest.max_inclination_deg is not None:
                assert summary["inclination_deg"] <= manifest.max_inclination_deg + 1e-9

    def test_candidate_config_limits_count(self) -> None:
        case = load_case(_smoke_case_dir())
        config = CandidateConfig(max_candidates=4, altitude_steps=2, inclination_steps=2, raan_steps=2, true_anomaly_steps=2)
        candidates = generate_candidates(case.manifest, config)
        assert len(candidates) <= 4


class TestSolutionIO:
    def test_write_empty_solution_valid(self, tmp_path: Path) -> None:
        solution_dir = tmp_path / "solution"
        path = write_solution(solution_dir, {}, [])
        assert path.exists()
        import json
        payload = json.loads(path.read_text())
        assert payload["added_satellites"] == []
        assert payload["actions"] == []

    def test_write_status_has_timing(self, tmp_path: Path) -> None:
        solution_dir = tmp_path / "solution"
        path = write_status(solution_dir, {"parse": 0.1}, {"num_nodes": 10})
        assert path.exists()
        import json
        payload = json.loads(path.read_text())
        assert payload["timing_s"]["parse"] == 0.1
        assert payload["num_nodes"] == 10


class TestSmoke:
    def test_full_solve_is_verifier_valid(self, tmp_path: Path) -> None:
        from benchmarks.relay_constellation.verifier import verify_solution

        result = solve(_smoke_case_dir(), tmp_path / "solution")
        solution_path = tmp_path / "solution" / "solution.json"
        verdict = verify_solution(_smoke_case_dir(), solution_path)
        assert verdict.valid is True
        assert result["summary"]["case_id"] == "case_0001"
        assert result["summary"]["num_candidate_satellites"] > 0


class TestCandidateSelection:
    def test_no_added_baseline(self) -> None:
        case = load_case(_smoke_case_dir())
        all_sats = dict(case.backbone_satellites)
        candidates = generate_candidates(case.manifest)
        all_sats.update(candidates)
        graphs = build_sample_graphs(case, all_sats)

        config = SelectionConfig(policy="no-added")
        selected, debug = select_candidates(case, graphs, candidates, config)
        assert len(selected) == 0
        assert debug["policy"] == "no-added"
        assert debug["baseline_total_weighted_service"] >= 0

    def test_greedy_selects_up_to_max_added(self) -> None:
        case = load_case(_smoke_case_dir())
        all_sats = dict(case.backbone_satellites)
        candidates = generate_candidates(case.manifest, CandidateConfig(max_candidates=4))
        all_sats.update(candidates)
        graphs = build_sample_graphs(case, all_sats)

        max_added = 2
        config = SelectionConfig(
            policy="greedy_marginal",
            max_added_satellites=max_added,
            evaluation_sample_stride=1,
        )
        selected, debug = select_candidates(case, graphs, candidates, config)
        assert len(selected) <= max_added
        assert debug["policy"] == "greedy_marginal"
        assert len(debug["scores_by_iteration"]) <= max_added

    def test_fixed_candidates_mode(self) -> None:
        case = load_case(_smoke_case_dir())
        all_sats = dict(case.backbone_satellites)
        candidates = generate_candidates(case.manifest)
        all_sats.update(candidates)
        graphs = build_sample_graphs(case, all_sats)

        fixed_ids = sorted(candidates.keys())[:2]
        config = SelectionConfig(
            policy="fixed",
            fixed_candidates=fixed_ids,
            evaluation_sample_stride=1,
        )
        selected, debug = select_candidates(case, graphs, candidates, config)
        assert list(selected.keys()) == fixed_ids
        assert debug["policy"] == "fixed"

    def test_fixed_candidates_rejects_unknown(self) -> None:
        case = load_case(_smoke_case_dir())
        all_sats = dict(case.backbone_satellites)
        candidates = generate_candidates(case.manifest)
        all_sats.update(candidates)
        graphs = build_sample_graphs(case, all_sats)

        config = SelectionConfig(
            policy="fixed",
            fixed_candidates=["nonexistent"],
            evaluation_sample_stride=1,
        )
        with pytest.raises(ValueError):
            select_candidates(case, graphs, candidates, config)
