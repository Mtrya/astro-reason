from __future__ import annotations

import json

from experiments.main_solver.run import _parse_json_verifier


def test_parse_json_verifier_records_aeossp_report() -> None:
    payload = {
        "valid": True,
        "metrics": {"CR": 0.5},
        "violations": [],
        "diagnostics": {"note": "ok"},
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"] == {"CR": 0.5}
    assert parsed["diagnostics"] == {"note": "ok"}


def test_parse_json_verifier_rejects_missing_valid() -> None:
    parsed = _parse_json_verifier("{}", 1)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None


def test_parse_json_verifier_rejects_extra_stdout() -> None:
    parsed = _parse_json_verifier('note\n{"valid": true}', 0)

    assert parsed["status"] == "error"
    assert parsed["valid"] is None
    assert "could not be parsed" in parsed["parse_error"]


def test_parse_json_verifier_handles_relay_constellation() -> None:
    """Relay verifier uses the same JSON schema as aeossp_standard."""
    payload = {
        "valid": True,
        "metrics": {
            "service_fraction": 0.694444,
            "worst_demand_service_fraction": 0.5,
            "mean_latency_ms": 42.0,
            "latency_p95_ms": 55.0,
            "num_added_satellites": 2,
        },
        "violations": [],
        "diagnostics": {"note": "ok"},
    }

    parsed = _parse_json_verifier(json.dumps(payload), 0)

    assert parsed["status"] == "valid"
    assert parsed["valid"] is True
    assert parsed["metrics"]["service_fraction"] == 0.694444
    assert parsed["metrics"]["num_added_satellites"] == 2
