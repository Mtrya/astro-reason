"""Standalone source package for the AEOSSP MWIS conflict-graph solver."""

from candidates import Candidate, CandidateConfig, CandidateSummary, generate_candidates
from case_io import AeosspCase, Mission, Satellite, Task, load_case
from graph import ConflictGraph, GraphStats, build_conflict_graph
from mwis import MwisConfig, MwisStats, select_weighted_independent_set
from validation import RepairConfig, RepairResult, ValidationReport, repair_candidates, validate_candidates

__all__ = [
    "AeosspCase",
    "Candidate",
    "CandidateConfig",
    "CandidateSummary",
    "ConflictGraph",
    "GraphStats",
    "Mission",
    "MwisConfig",
    "MwisStats",
    "RepairConfig",
    "RepairResult",
    "Satellite",
    "Task",
    "ValidationReport",
    "build_conflict_graph",
    "generate_candidates",
    "load_case",
    "repair_candidates",
    "select_weighted_independent_set",
    "validate_candidates",
]
