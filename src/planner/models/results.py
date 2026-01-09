"""Result dataclasses for staging and commit operations."""

from dataclasses import dataclass, field
from typing import List, Dict

from .metrics import PlanMetrics
from .action import PlannerAction


@dataclass
class Violation:
    """Represents a constraint violation."""
    action_id: str
    violation_type: str  # "time_conflict", "power", "storage", "access_invalid"
    message: str
    conflicting_action_ids: List[str] | None = None


@dataclass
class PlanStatus:
    """Current plan status with staged actions and metrics."""
    actions: Dict[str, PlannerAction] = field(default_factory=dict)
    metrics: PlanMetrics = field(default_factory=PlanMetrics)


@dataclass
class StageResult:
    """Result of staging an action."""
    action_id: str
    staged: bool
    projected_metrics: PlanMetrics | None = None


@dataclass
class UnstageResult:
    """Result of unstaging an action."""
    action_id: str
    unstaged: bool
    projected_metrics: PlanMetrics | None = None


@dataclass
class CommitResult:
    """Result of committing a plan."""
    valid: bool
    violations: List[Violation] = field(default_factory=list)
    metrics: PlanMetrics | None = None
    plan_json_path: str | None = None
