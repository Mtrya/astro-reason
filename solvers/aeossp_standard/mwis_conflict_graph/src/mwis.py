"""Deterministic weighted independent-set selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from candidates import Candidate
from graph import ConflictGraph, connected_components


@dataclass(frozen=True, slots=True)
class MwisConfig:
    max_exact_component_size: int = 20


@dataclass(slots=True)
class MwisStats:
    selected_candidate_count: int
    selected_total_weight: float
    exact_component_count: int
    greedy_component_count: int
    independent_set_valid: bool

    def as_dict(self) -> dict:
        return asdict(self)


def greedy_priority(candidate: Candidate, degree: int) -> tuple:
    return (-candidate.task_weight, candidate.end_offset_s, degree, candidate.candidate_id)


def validate_independent_set(
    selected_candidate_ids: set[str],
    adjacency: dict[str, set[str]],
) -> bool:
    for candidate_id in selected_candidate_ids:
        if adjacency.get(candidate_id, set()) & selected_candidate_ids:
            return False
    return True


def _selected_key(selected: set[str], candidate_by_id: dict[str, Candidate]) -> tuple:
    total_weight = sum(candidate_by_id[candidate_id].task_weight for candidate_id in selected)
    total_count = len(selected)
    total_completion = sum(candidate_by_id[candidate_id].end_offset_s for candidate_id in selected)
    return (
        round(total_weight, 12),
        total_count,
        -total_completion,
        tuple(sorted(selected)),
    )


def _is_better(
    candidate_set: set[str],
    incumbent_set: set[str],
    candidate_by_id: dict[str, Candidate],
) -> bool:
    return _selected_key(candidate_set, candidate_by_id) > _selected_key(
        incumbent_set,
        candidate_by_id,
    )


def solve_exact_component(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
) -> set[str]:
    ordered = sorted(
        component,
        key=lambda candidate_id: greedy_priority(
            candidate_by_id[candidate_id],
            len(adjacency[candidate_id]),
        ),
    )
    suffix_weight: list[float] = [0.0] * (len(ordered) + 1)
    for index in range(len(ordered) - 1, -1, -1):
        suffix_weight[index] = suffix_weight[index + 1] + candidate_by_id[ordered[index]].task_weight

    best: set[str] = set()

    def search(index: int, selected: set[str], blocked: set[str]) -> None:
        nonlocal best
        current_weight = sum(candidate_by_id[candidate_id].task_weight for candidate_id in selected)
        best_weight = sum(candidate_by_id[candidate_id].task_weight for candidate_id in best)
        if current_weight + suffix_weight[index] < best_weight - 1.0e-9:
            return
        if index >= len(ordered):
            if _is_better(selected, best, candidate_by_id):
                best = set(selected)
            return

        candidate_id = ordered[index]
        if candidate_id not in blocked:
            search(
                index + 1,
                selected | {candidate_id},
                blocked | adjacency[candidate_id],
            )
        search(index + 1, selected, blocked | {candidate_id})

    search(0, set(), set())
    return best


def solve_greedy_component(
    component: list[str],
    candidate_by_id: dict[str, Candidate],
    adjacency: dict[str, set[str]],
) -> set[str]:
    selected: set[str] = set()
    for candidate_id in sorted(
        component,
        key=lambda item: greedy_priority(candidate_by_id[item], len(adjacency[item])),
    ):
        if not adjacency[candidate_id] & selected:
            selected.add(candidate_id)
    return selected


def select_weighted_independent_set(
    candidates: list[Candidate],
    graph: ConflictGraph,
    config: MwisConfig | None = None,
) -> tuple[list[Candidate], MwisStats]:
    config = config or MwisConfig()
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    selected_ids: set[str] = set()
    exact_components = 0
    greedy_components = 0

    for component in connected_components(graph.adjacency):
        if len(component) <= config.max_exact_component_size:
            component_selected = solve_exact_component(
                component,
                candidate_by_id,
                graph.adjacency,
            )
            exact_components += 1
        else:
            component_selected = solve_greedy_component(
                component,
                candidate_by_id,
                graph.adjacency,
            )
            greedy_components += 1
        selected_ids.update(component_selected)

    valid = validate_independent_set(selected_ids, graph.adjacency)
    selected = sorted(
        (candidate_by_id[candidate_id] for candidate_id in selected_ids),
        key=lambda item: (item.start_offset_s, item.satellite_id, item.task_id, item.candidate_id),
    )
    stats = MwisStats(
        selected_candidate_count=len(selected),
        selected_total_weight=sum(candidate.task_weight for candidate in selected),
        exact_component_count=exact_components,
        greedy_component_count=greedy_components,
        independent_set_valid=valid,
    )
    return selected, stats
