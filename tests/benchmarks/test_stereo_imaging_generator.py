from __future__ import annotations

import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

import benchmarks.stereo_imaging.generator.build as generator_build
import benchmarks.stereo_imaging.generator.run as generator_run
from benchmarks.stereo_imaging.generator.build import load_generator_config
from benchmarks.stereo_imaging.generator.feasibility import (
    CandidateObservation,
    FeasibilityAuditResult,
    _audit_case_feasibility_streaming,
    _evaluate_candidate_pairs,
    audit_case_feasibility,
)
from benchmarks.stereo_imaging.generator.sources import (
    CELESTRAK_CSV_NAME,
    CELESTRAK_EARTH_RESOURCES_URL,
    CELESTRAK_RAW_NAME,
    CELESTRAK_SNAPSHOT_EPOCH_UTC,
    SourceFetchResult,
    WORLD_CITIES_DATASET,
    WORLD_CITIES_FILENAME,
)
from benchmarks.stereo_imaging.verifier.models import (
    DerivedObservation,
    Mission,
    ObservationAction,
    SatelliteDef,
    TargetDef,
)


def test_generator_uses_benchmark_satellite_catalog_when_split_omits_catalog() -> None:
    catalog = generator_build._satellite_catalog_from_config(
        {
            "min_per_case": 10,
            "max_per_case": 12,
        },
        label="splits.test.satellites",
    )

    assert len(catalog) >= 20
    assert catalog[38012]["id"] == "sat_pleiades_1a"
    assert catalog[38755]["id"] == "sat_spot_6"


def _write_splits_yaml(path: Path, *, snapshot_epoch_utc: str = CELESTRAK_SNAPSHOT_EPOCH_UTC) -> None:
    payload = {
        "example_smoke_case": "test/case_0001",
        "source": {
            "celestrak": {
                "kind": "vendored_subset",
                "url": CELESTRAK_EARTH_RESOURCES_URL,
                "snapshot_epoch_utc": snapshot_epoch_utc,
            },
            "world_cities": {
                "kind": "kaggle_dataset",
                "dataset": WORLD_CITIES_DATASET,
                "page_url": "https://www.kaggle.com/datasets/juanmah/world-cities",
            },
            "lookup_tables": {
                "kind": "vendored_lookup_tables",
                "module": "benchmarks/stereo_imaging/generator/lookup_tables.py",
            },
        },
        "splits": {
            "test": {
                "seed": 20260406,
                "case_count": 1,
                "case_seed_stride": 10007,
                "mission": {
                    "base_horizon_start": "2026-04-06T00:00:00Z",
                    "case_start_spacing_hours": 6,
                    "horizon_duration_s": 172800,
                    "allow_cross_satellite_stereo": False,
                    "max_stereo_pair_separation_s": 7200.0,
                    "validity_thresholds": {
                        "min_overlap_fraction": 0.8,
                        "min_convergence_deg": 5.0,
                        "max_convergence_deg": 45.0,
                        "max_pixel_scale_ratio": 1.5,
                        "min_solar_elevation_deg": 10.0,
                        "near_nadir_anchor_max_off_nadir_deg": 10.0,
                    },
                    "quality_model": {
                        "pair_weights": {
                            "geometry": 0.5,
                            "overlap": 0.35,
                            "resolution": 0.15,
                        },
                        "tri_stereo_bonus_by_scene": {
                            "urban_structured": 0.12,
                            "rugged": 0.10,
                            "vegetated": 0.08,
                            "open": 0.05,
                        },
                    },
                },
                "feasibility_guard": {
                    "max_generation_attempts_per_case": 3,
                    "access_sample_step_s": 60.0,
                    "max_candidate_observations_per_access": 4,
                    "overlap_samples": 40,
                },
                "targets": {
                    "min_count": 4,
                    "max_count": 4,
                    "urban_target_divisor": 2,
                    "min_urban_population": 1000,
                    "max_abs_latitude_deg": 70.0,
                    "non_urban_jitter_deg": 0.2,
                    "aoi_radius_min_m": 2500.0,
                    "aoi_radius_max_m": 2500.0,
                },
                "satellites": {
                    "min_per_case": 2,
                    "max_per_case": 2,
                    "catalog": {
                        "38012": {
                            "id": "sat_pleiades_1a",
                            "pixel_ifov_deg": 0.00004,
                            "cross_track_pixels": 20000,
                            "max_off_nadir_deg": 30.0,
                            "max_slew_velocity_deg_per_s": 1.95,
                            "max_slew_acceleration_deg_per_s2": 0.95,
                            "settling_time_s": 1.9,
                            "min_obs_duration_s": 2.0,
                            "max_obs_duration_s": 60.0,
                        },
                        "38755": {
                            "id": "sat_spot_6",
                            "pixel_ifov_deg": 0.00012,
                            "cross_track_pixels": 12000,
                            "max_off_nadir_deg": 30.0,
                            "max_slew_velocity_deg_per_s": 2.35,
                            "max_slew_acceleration_deg_per_s2": 1.15,
                            "settling_time_s": 1.35,
                            "min_obs_duration_s": 2.0,
                            "max_obs_duration_s": 60.0,
                        },
                    },
                },
            }
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_source_tree(source_dir: Path) -> None:
    celestrak_dir = source_dir / "celestrak"
    celestrak_dir.mkdir(parents=True, exist_ok=True)
    with (celestrak_dir / CELESTRAK_CSV_NAME).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "norad_catalog_id", "tle_line1", "tle_line2", "epoch_iso"],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "name": "PLEIADES 1A",
                    "norad_catalog_id": "38012",
                    "tle_line1": "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994",
                    "tle_line2": "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501",
                    "epoch_iso": "2026-04-06T05:38:58.292160Z",
                },
                {
                    "name": "SPOT 6",
                    "norad_catalog_id": "38755",
                    "tle_line1": "1 38755U 12047A   26096.23426606  .00000498  00000+0  11693-3 0  9997",
                    "tle_line2": "2 38755  98.2167 164.3679 0001434  83.0887 277.0475 14.58566315722563",
                    "epoch_iso": "2026-04-06T05:37:20.587584Z",
                },
            ]
        )
    (celestrak_dir / CELESTRAK_RAW_NAME).write_text("cached\n", encoding="utf-8")

    cities_dir = source_dir / "world_cities"
    cities_dir.mkdir(parents=True, exist_ok=True)
    (cities_dir / WORLD_CITIES_FILENAME).write_text(
        "\n".join(
            [
                "name,country,lat,lng,population",
                "Paris,France,48.8566,2.3522,2161000",
                "Tokyo,Japan,35.6762,139.6503,13960000",
                "Sydney,Australia,-33.8688,151.2093,5312000",
                "Nairobi,Kenya,-1.2864,36.8172,4397000",
                "Santiago,Chile,-33.4489,-70.6693,5614000",
                "Ottawa,Canada,45.4215,-75.6972,994837",
                "Longyearbyen,Norway,78.2232,15.6267,2368",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _mission_model(
    *,
    allow_cross_satellite: bool = True,
    max_pair_separation_s: float = 7200.0,
) -> Mission:
    return Mission(
        horizon_start=datetime(2026, 4, 6, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 4, 7, 0, 0, tzinfo=UTC),
        allow_cross_satellite_stereo=allow_cross_satellite,
        max_stereo_pair_separation_s=max_pair_separation_s,
        min_overlap_fraction=0.8,
        min_convergence_deg=5.0,
        max_convergence_deg=45.0,
        max_pixel_scale_ratio=1.5,
        min_solar_elevation_deg=10.0,
        near_nadir_anchor_max_off_nadir_deg=10.0,
        pair_weights={"geometry": 0.5, "overlap": 0.35, "resolution": 0.15},
        tri_stereo_bonus_by_scene={
            "urban_structured": 0.12,
            "rugged": 0.10,
            "vegetated": 0.08,
            "open": 0.05,
        },
    )


def _sat_def(sat_id: str) -> SatelliteDef:
    return SatelliteDef(
        sat_id=sat_id,
        norad_catalog_id=1,
        tle_line1="1 00001U 00001A   26096.00000000  .00000000  00000+0  00000+0 0  9991",
        tle_line2="2 00001  98.0000 000.0000 0001000 000.0000 000.0000 14.00000000000001",
        pixel_ifov_deg=0.00004,
        cross_track_pixels=12000,
        max_off_nadir_deg=30.0,
        max_slew_velocity_deg_per_s=2.0,
        max_slew_acceleration_deg_per_s2=1.0,
        settling_time_s=1.0,
        min_obs_duration_s=2.0,
        max_obs_duration_s=60.0,
    )


def _target_def(target_id: str = "t1") -> TargetDef:
    return TargetDef(
        target_id=target_id,
        latitude_deg=0.0,
        longitude_deg=0.0,
        aoi_radius_m=2500.0,
        elevation_ref_m=0.0,
        scene_type="urban_structured",
    )


def _candidate(
    *,
    sat_id: str,
    action_index: int,
    start_second: int,
    target_id: str = "t1",
) -> CandidateObservation:
    start = datetime(2026, 4, 6, 1, 0, 0, tzinfo=UTC) + timedelta(seconds=start_second)
    end = start + timedelta(seconds=2)
    action = ObservationAction(sat_id, target_id, start, end, 0.0, 0.0)
    derived = DerivedObservation(
        satellite_id=sat_id,
        target_id=target_id,
        action_index=action_index,
        start_time=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        midpoint_time=(start + (end - start) / 2).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sat_position_ecef_m=[0.0, 0.0, 0.0],
        sat_velocity_ecef_mps=[0.0, 0.0, 0.0],
        boresight_off_nadir_deg=0.0,
        boresight_azimuth_deg=0.0,
        solar_elevation_deg=45.0,
        solar_azimuth_deg=180.0,
        effective_pixel_scale_m=0.5,
        access_interval_id=f"{sat_id}::{target_id}::0",
        slant_range_m=700000.0,
    )
    return CandidateObservation(action=action, derived=derived)


def _accepting_audit(**_kwargs) -> FeasibilityAuditResult:
    return FeasibilityAuditResult(
        feasible=True,
        diagnostics={
            "satellites_with_access": ["sat_a"],
            "candidate_observation_count": 2,
        },
    )


def test_main_requires_splits_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["run.py"])

    with pytest.raises(SystemExit) as exc_info:
        generator_run.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "usage:" in captured.err.lower()


def test_load_generator_config_rejects_unsupported_snapshot_epoch(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path, snapshot_epoch_utc="2026-04-07T00:00:00Z")

    with pytest.raises(ValueError, match="cached CelesTrak snapshot epoch"):
        load_generator_config(splits_path)


def test_load_generator_config_rejects_removed_cross_date_field(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    payload = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
    payload["splits"]["test"]["mission"]["allow_cross_date_stereo"] = False
    splits_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="allow_cross_date_stereo"):
        load_generator_config(splits_path)


def test_load_generator_config_rejects_invalid_pair_separation(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    payload = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
    payload["splits"]["test"]["mission"]["max_stereo_pair_separation_s"] = 0.0
    splits_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="max_stereo_pair_separation_s"):
        load_generator_config(splits_path)


def test_load_generator_config_rejects_invalid_attempt_limit(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    payload = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
    payload["splits"]["test"]["feasibility_guard"]["max_generation_attempts_per_case"] = 0
    splits_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="max_generation_attempts_per_case"):
        load_generator_config(splits_path)


def test_load_generator_config_rejects_fractional_overlap_samples(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    payload = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
    payload["splits"]["test"]["feasibility_guard"]["overlap_samples"] = 0.5
    splits_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="overlap_samples"):
        load_generator_config(splits_path)


def test_feasibility_guard_rejects_case_without_candidate_access() -> None:
    result = _evaluate_candidate_pairs(
        case_id="case_0001",
        mission=_mission_model(),
        satellites={"sat_a": _sat_def("sat_a")},
        targets={"t1": _target_def()},
        sf_sats={"sat_a": object()},
        target_ecef={},
        candidates=[],
        overlap_samples=10,
    )

    assert result.feasible is False
    assert result.diagnostics["candidate_observation_count"] == 0
    assert result.diagnostics["most_common_rejection_reason"] == "no_candidate_access"


def test_feasibility_guard_rejects_fractional_overlap_samples() -> None:
    with pytest.raises(ValueError, match="overlap_samples"):
        audit_case_feasibility(
            case_id="case_0001",
            mission_doc={},
            satellite_rows=[],
            target_rows=[],
            guard_config={"overlap_samples": 0.5},
        )


def test_feasibility_guard_accepts_cross_satellite_candidate_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_evaluate_pair(**kwargs):
        return {
            "valid_pair": True,
            "q_pair": 0.9,
            "stereo_mode": kwargs["stereo_mode"],
            "satellite_ids": [
                kwargs["first_derived"].satellite_id,
                kwargs["second_derived"].satellite_id,
            ],
        }

    monkeypatch.setattr(
        "benchmarks.stereo_imaging.generator.feasibility._evaluate_stereo_pair",
        fake_evaluate_pair,
    )

    result = _evaluate_candidate_pairs(
        case_id="case_0001",
        mission=_mission_model(allow_cross_satellite=True, max_pair_separation_s=180.0),
        satellites={"sat_a": _sat_def("sat_a"), "sat_b": _sat_def("sat_b")},
        targets={"t1": _target_def()},
        sf_sats={"sat_a": object(), "sat_b": object()},
        target_ecef={},
        candidates=[
            _candidate(sat_id="sat_a", action_index=0, start_second=0),
            _candidate(sat_id="sat_b", action_index=1, start_second=60),
        ],
        overlap_samples=10,
    )

    assert result.feasible is True
    assert result.diagnostics["candidate_cross_satellite_pair_count"] == 1
    assert result.diagnostics["accepted_pair"]["stereo_mode"] == "cross_satellite"


def test_streaming_feasibility_guard_stops_after_first_feasible_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned_targets: list[str] = []

    def fake_find_candidates(mission, satellites, target, sf_sats, target_pos, **kwargs):
        del mission, satellites, sf_sats, target_pos, kwargs
        scanned_targets.append(target.target_id)
        if target.target_id != "t2":
            return []
        return [
            _candidate(sat_id="sat_a", action_index=0, start_second=0, target_id="t2"),
            _candidate(sat_id="sat_b", action_index=1, start_second=60, target_id="t2"),
        ]

    def fake_evaluate_pair(**kwargs):
        return {
            "valid_pair": True,
            "q_pair": 0.9,
            "stereo_mode": kwargs["stereo_mode"],
        }

    monkeypatch.setattr(
        "benchmarks.stereo_imaging.generator.feasibility._find_candidate_observations_for_target",
        fake_find_candidates,
    )
    monkeypatch.setattr(
        "benchmarks.stereo_imaging.generator.feasibility._evaluate_stereo_pair",
        fake_evaluate_pair,
    )

    result = _audit_case_feasibility_streaming(
        case_id="case_0001",
        mission=_mission_model(allow_cross_satellite=True, max_pair_separation_s=180.0),
        satellites={"sat_a": _sat_def("sat_a"), "sat_b": _sat_def("sat_b")},
        targets={"t1": _target_def("t1"), "t2": _target_def("t2"), "t3": _target_def("t3")},
        sf_sats={"sat_a": object(), "sat_b": object()},
        target_ecef={"t1": object(), "t2": object(), "t3": object()},
        access_sample_step_s=60.0,
        max_candidates_per_access=4,
        overlap_samples=10,
    )

    assert result.feasible is True
    assert scanned_targets == ["t1", "t2"]
    assert result.diagnostics["targets_scanned_before_accept"] == 2
    assert result.diagnostics["candidate_observation_count_before_accept"] == 2


def test_main_rejects_invalid_max_abs_latitude(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    payload = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
    payload["splits"]["test"]["targets"]["max_abs_latitude_deg"] = 0.0
    splits_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    download_dir = tmp_path / "sources"
    output_dir = tmp_path / "output"

    def fake_fetch_all_sources(dest_dir: Path, *, force_download: bool = False):
        del force_download
        _write_source_tree(dest_dir)
        return {
            "celestrak": SourceFetchResult(
                "celestrak",
                [dest_dir / "celestrak" / CELESTRAK_CSV_NAME],
                {
                    "record_count": 2,
                    "sha256": "fake",
                    "vendored_snapshot": True,
                },
            ),
            "world_cities": SourceFetchResult(
                "world_cities",
                [dest_dir / "world_cities" / WORLD_CITIES_FILENAME],
                {"sha256": "fake"},
            ),
        }

    monkeypatch.setattr(generator_run, "fetch_all_sources", fake_fetch_all_sources)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--download-dir",
            str(download_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    with pytest.raises(ValueError, match=r"targets\.max_abs_latitude_deg"):
        generator_run.main()


def test_sources_only_mode_is_operational_and_skips_dataset_emission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    download_dir = tmp_path / "sources"
    output_dir = tmp_path / "output"
    captured: dict[str, object] = {}

    def fake_fetch_all_sources(dest_dir: Path, *, force_download: bool = False):
        _write_source_tree(dest_dir)
        captured["download_dir"] = dest_dir
        captured["force_download"] = force_download
        return {
            "celestrak": SourceFetchResult(
                "celestrak",
                [dest_dir / "celestrak" / CELESTRAK_CSV_NAME],
                {
                    "record_count": 2,
                    "sha256": "fake",
                    "vendored_snapshot": True,
                },
            ),
            "world_cities": SourceFetchResult(
                "world_cities",
                [dest_dir / "world_cities" / WORLD_CITIES_FILENAME],
                {"sha256": "fake"},
            ),
        }

    monkeypatch.setattr(generator_run, "fetch_all_sources", fake_fetch_all_sources)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--download-dir",
            str(download_dir),
            "--output-dir",
            str(output_dir),
            "--sources-only",
            "--force-download",
        ],
    )

    assert generator_run.main() == 0
    assert captured["download_dir"] == download_dir
    assert captured["force_download"] is True
    assert (download_dir / "provenance.json").exists()
    assert not (output_dir / "index.json").exists()


def test_main_builds_split_aware_dataset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    download_dir = tmp_path / "sources"
    output_dir = tmp_path / "output"

    def fake_fetch_all_sources(dest_dir: Path, *, force_download: bool = False):
        del force_download
        _write_source_tree(dest_dir)
        return {
            "celestrak": SourceFetchResult(
                "celestrak",
                [dest_dir / "celestrak" / CELESTRAK_CSV_NAME],
                {
                    "record_count": 2,
                    "sha256": "fake",
                    "vendored_snapshot": True,
                },
            ),
            "world_cities": SourceFetchResult(
                "world_cities",
                [dest_dir / "world_cities" / WORLD_CITIES_FILENAME],
                {"sha256": "fake"},
            ),
        }

    monkeypatch.setattr(generator_run, "fetch_all_sources", fake_fetch_all_sources)
    monkeypatch.setattr(generator_build, "audit_case_feasibility", _accepting_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--download-dir",
            str(download_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert generator_run.main() == 0
    assert (output_dir / "cases" / "test" / "case_0001" / "mission.yaml").exists()
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    assert index["example_smoke_case"] == "test/case_0001"
    assert index["cases"][0]["split"] == "test"
    assert index["cases"][0]["path"] == "cases/test/case_0001"
    assert index["spec_version"] == "v4"
    mission = yaml.safe_load(
        (output_dir / "cases" / "test" / "case_0001" / "mission.yaml").read_text(
            encoding="utf-8"
        )
    )["mission"]
    assert mission["max_stereo_pair_separation_s"] == pytest.approx(7200.0)
    assert "allow_cross_date_stereo" not in mission
    targets = yaml.safe_load(
        (output_dir / "cases" / "test" / "case_0001" / "targets.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert targets
    assert all(abs(float(target["latitude_deg"])) < 70.0 for target in targets)


def test_main_exhausts_feasibility_attempts_without_writing_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    payload = yaml.safe_load(splits_path.read_text(encoding="utf-8"))
    payload["splits"]["test"]["feasibility_guard"]["max_generation_attempts_per_case"] = 2
    splits_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    download_dir = tmp_path / "sources"
    output_dir = tmp_path / "output"

    def fake_fetch_all_sources(dest_dir: Path, *, force_download: bool = False):
        del force_download
        _write_source_tree(dest_dir)
        return {
            "celestrak": SourceFetchResult(
                "celestrak",
                [dest_dir / "celestrak" / CELESTRAK_CSV_NAME],
                {
                    "record_count": 2,
                    "sha256": "fake",
                    "vendored_snapshot": True,
                },
            ),
            "world_cities": SourceFetchResult(
                "world_cities",
                [dest_dir / "world_cities" / WORLD_CITIES_FILENAME],
                {"sha256": "fake"},
            ),
        }

    def rejecting_audit(**_kwargs):
        return FeasibilityAuditResult(
            feasible=False,
            diagnostics={
                "satellites_with_access": [],
                "candidate_observation_count": 0,
                "candidate_same_satellite_pair_count": 0,
                "candidate_cross_satellite_pair_count": 0,
                "most_common_rejection_reason": "no_candidate_access",
            },
        )

    monkeypatch.setattr(generator_run, "fetch_all_sources", fake_fetch_all_sources)
    monkeypatch.setattr(generator_build, "audit_case_feasibility", rejecting_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--download-dir",
            str(download_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    with pytest.raises(RuntimeError, match="exhausted 2 generation attempts"):
        generator_run.main()
    assert not (output_dir / "cases" / "test" / "case_0001").exists()


def test_main_retries_until_feasibility_guard_accepts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    splits_path = tmp_path / "splits.yaml"
    _write_splits_yaml(splits_path)
    download_dir = tmp_path / "sources"
    output_dir = tmp_path / "output"

    def fake_fetch_all_sources(dest_dir: Path, *, force_download: bool = False):
        del force_download
        _write_source_tree(dest_dir)
        return {
            "celestrak": SourceFetchResult(
                "celestrak",
                [dest_dir / "celestrak" / CELESTRAK_CSV_NAME],
                {
                    "record_count": 2,
                    "sha256": "fake",
                    "vendored_snapshot": True,
                },
            ),
            "world_cities": SourceFetchResult(
                "world_cities",
                [dest_dir / "world_cities" / WORLD_CITIES_FILENAME],
                {"sha256": "fake"},
            ),
        }

    calls = {"count": 0}

    def flaky_audit(**_kwargs):
        calls["count"] += 1
        return FeasibilityAuditResult(
            feasible=calls["count"] == 2,
            diagnostics={
                "satellites_with_access": ["sat_a"],
                "candidate_observation_count": 2,
                "candidate_same_satellite_pair_count": 1,
                "candidate_cross_satellite_pair_count": 0,
                "most_common_rejection_reason": None,
            },
        )

    monkeypatch.setattr(generator_run, "fetch_all_sources", fake_fetch_all_sources)
    monkeypatch.setattr(generator_build, "audit_case_feasibility", flaky_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            str(splits_path),
            "--download-dir",
            str(download_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert generator_run.main() == 0
    assert calls["count"] == 2
    assert (output_dir / "cases" / "test" / "case_0001" / "mission.yaml").exists()
