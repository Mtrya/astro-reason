"""Public API for the relay_constellation verifier."""

from .engine import verify, verify_solution
from .io import load_case, load_solution
from .models import (
    DEFAULT_DATASET_DIR,
    LIGHT_SPEED_M_S,
    NUMERICAL_EPS,
    OrbitSummary,
    PathCandidate,
    RelayAction,
    RelayCase,
    RelayDemand,
    RelayEndpoint,
    RelayManifest,
    RelaySatellite,
    RelaySolution,
    ValidatedAction,
    VerificationResult,
)

__all__ = [
    "DEFAULT_DATASET_DIR",
    "LIGHT_SPEED_M_S",
    "NUMERICAL_EPS",
    "OrbitSummary",
    "PathCandidate",
    "RelayAction",
    "RelayCase",
    "RelayDemand",
    "RelayEndpoint",
    "RelayManifest",
    "RelaySatellite",
    "RelaySolution",
    "ValidatedAction",
    "VerificationResult",
    "load_case",
    "load_solution",
    "verify",
    "verify_solution",
]
