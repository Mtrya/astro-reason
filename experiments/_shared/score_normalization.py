"""Reader-facing score normalization helpers for experiment aggregation.

These functions convert benchmark-native verifier metrics into percentage-like
scores where higher is better. They are experiment post-processing helpers, not
benchmark verifier logic.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from typing import Any

DEFAULT_SCARCITY_GAMMA = 2.0
DEFAULT_REVISIT_POWER = 2.0


def is_number(value: Any) -> bool:
    """Return true for numeric scalar values, excluding booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def to_float(value: Any) -> float | None:
    """Convert a numeric scalar to float, returning None for missing or nonnumeric values."""
    return float(value) if is_number(value) else None


def clip01(value: float) -> float:
    """Clamp a value to the closed unit interval."""
    return min(1.0, max(0.0, float(value)))


def pct(value: float) -> float:
    """Convert a unit-interval score to percentage points."""
    return 100.0 * value


def ratio_score(
    numerator: float | int | None,
    denominator: float | int | None,
    *,
    clip: bool = True,
) -> float | None:
    """Normalize a numerator by a positive denominator.

    By default the result is clipped to [0, 1], which is appropriate for
    reader-facing scores that should not exceed full credit.
    """
    numerator_float = to_float(numerator)
    denominator_float = to_float(denominator)
    if numerator_float is None or denominator_float is None or denominator_float <= 0:
        return None
    score = numerator_float / denominator_float
    return clip01(score) if clip else score


def ratio_score_pct(
    numerator: float | int | None,
    denominator: float | int | None,
    *,
    clip: bool = True,
) -> float | None:
    """Return ratio_score as percentage points."""
    score = ratio_score(numerator, denominator, clip=clip)
    return None if score is None else pct(score)


def lower_score(value: float | int | None, cap: float | int | None) -> float | None:
    """Score a lower-is-better metric against a positive cap.

    A value of 0 receives 1.0, values at or above cap receive 0.0, and values in
    between are linearly interpolated.
    """
    value_float = to_float(value)
    cap_float = to_float(cap)
    if value_float is None or cap_float is None or cap_float <= 0:
        return None
    return 1.0 - clip01(value_float / cap_float)


def scarcity_bonus(
    count: float | int | None,
    *,
    n_min: float | int | None,
    n_max: float | int | None,
    gamma: float = DEFAULT_SCARCITY_GAMMA,
) -> float | None:
    """Score use of a scarce count resource with nonlinear late-stage rewards.

    The score is 0.0 at n_max and 1.0 at n_min. With gamma > 1, improvements
    near n_min are worth more than early reductions from n_max.
    """
    count_float = to_float(count)
    min_float = to_float(n_min)
    max_float = to_float(n_max)
    if (
        count_float is None
        or min_float is None
        or max_float is None
        or max_float <= min_float
        or gamma <= 0
    ):
        return None
    return clip01((max_float - count_float) / (max_float - min_float)) ** gamma


def score_against_baseline_pct(
    *,
    value: float | int,
    baseline: float | int,
    direction: str,
) -> float | None:
    """Compare a metric value against a same-case baseline as percentage points.

    This is used by plots that ask "how good is this run relative to a fixed
    baseline?" It is intentionally separate from normalized_score formulas.
    """
    value_float = to_float(value)
    baseline_float = to_float(baseline)
    if value_float is None or baseline_float is None or baseline_float <= 0 or value_float < 0:
        return None
    if direction == "maximize":
        return pct(value_float / baseline_float)
    if direction == "minimize":
        if value_float <= 0:
            return None
        return pct(baseline_float / value_float)
    raise ValueError(f"Unknown metric direction: {direction}")


def aeossp_standard_score_pct(
    *,
    wcr: float | int | None,
    cr: float | int | None,
    tat: float | int | None,
    pc: float | int | None,
    horizon_seconds: float | int | None,
    case_energy_budget: float | int | None,
) -> float | None:
    """Compute the AEOSSP Standard normalized score.

    WCR is primary, CR is secondary, and TAT/PC are lower-is-better resource
    terms normalized by case-derived caps.
    """
    tat_score = lower_score(tat, horizon_seconds)
    pc_score = lower_score(pc, case_energy_budget)
    wcr_float = to_float(wcr)
    cr_float = to_float(cr)
    if None in (tat_score, pc_score, wcr_float, cr_float):
        return None
    return pct(
        0.45 * clip01(wcr_float)
        + 0.20 * clip01(cr_float)
        + 0.20 * tat_score
        + 0.15 * pc_score
    )


def regional_coverage_score_pct(
    *,
    weighted_coverage_ratio: float | int | None,
    coverage_ratio: float | int | None,
    num_actions: float | int | None,
    min_battery_wh: float | int | None,
    max_actions_total: float | int | None,
    battery_capacity_wh: float | int | None,
) -> float | None:
    """Compute the Regional Coverage normalized score.

    Weighted coverage is primary, with secondary credit for raw coverage,
    fewer actions, and retained battery margin.
    """
    action_score = lower_score(num_actions, max_actions_total)
    battery_score = ratio_score(min_battery_wh, battery_capacity_wh)
    weighted_float = to_float(weighted_coverage_ratio)
    coverage_float = to_float(coverage_ratio)
    if None in (action_score, battery_score, weighted_float, coverage_float):
        return None
    return pct(
        0.50 * clip01(weighted_float)
        + 0.20 * clip01(coverage_float)
        + 0.15 * action_score
        + 0.15 * battery_score
    )


def relay_constellation_score_pct(
    *,
    service_fraction: float | int | None,
    worst_demand_service_fraction: float | int | None,
    num_added_satellites: float | int | None = None,
    mean_latency_ms: float | int | None = None,
    latency_p95_ms: float | int | None = None,
    min_added_satellites: float | int | None = None,
    max_added_satellites: float | int | None = None,
    latency_cap_ms: float | int | None = None,
    gamma: float = DEFAULT_SCARCITY_GAMMA,
) -> float | None:
    """Compute the Relay Constellation gated normalized score.

    Service quality fills the bottom 70 points. Only full-service solutions can
    receive added-satellite and latency bonus points above that gate.
    """
    service = to_float(service_fraction)
    worst_service = to_float(worst_demand_service_fraction)
    if service is None or worst_service is None:
        return None

    service_core = 0.75 * clip01(service) + 0.25 * clip01(worst_service)
    if service < 1.0:
        return 70.0 * service_core

    satellite_score = scarcity_bonus(
        num_added_satellites,
        n_min=min_added_satellites,
        n_max=max_added_satellites,
        gamma=gamma,
    )
    mean_latency_score = lower_score(mean_latency_ms, latency_cap_ms)
    p95_latency_score = lower_score(latency_p95_ms, latency_cap_ms)
    if None in (satellite_score, mean_latency_score, p95_latency_score):
        return 70.0
    latency_score = 0.60 * mean_latency_score + 0.40 * p95_latency_score
    return 70.0 + 30.0 * (0.75 * satellite_score + 0.25 * latency_score)


def revisit_target_gap_score(
    *,
    max_gap_hours: float | int,
    expected_revisit_hours: float | int,
    horizon_hours: float | int,
    power: float = DEFAULT_REVISIT_POWER,
) -> float:
    """Score one revisit target's maximum gap on the smooth threshold curve."""
    if max_gap_hours >= horizon_hours:
        return 0.0
    if max_gap_hours <= expected_revisit_hours:
        return 1.0
    denominator = horizon_hours - expected_revisit_hours
    if denominator <= 0 or power <= 0:
        return 0.0
    ratio = (horizon_hours - max_gap_hours) / denominator
    return clip01(ratio) ** power


def revisit_target_gap_score_pct(
    *,
    max_gap_hours: float | int,
    expected_revisit_hours: float | int,
    horizon_hours: float | int,
    power: float = DEFAULT_REVISIT_POWER,
) -> float:
    """Return revisit_target_gap_score as percentage points."""
    return pct(
        revisit_target_gap_score(
            max_gap_hours=max_gap_hours,
            expected_revisit_hours=expected_revisit_hours,
            horizon_hours=horizon_hours,
            power=power,
        )
    )


def revisit_gap_score_from_target_summaries(
    target_summaries: Iterable[Mapping[str, Any]],
    *,
    horizon_hours: float | int,
    power: float = DEFAULT_REVISIT_POWER,
) -> float | None:
    """Average target-level revisit gap scores from verifier target summaries."""
    target_scores: list[float] = []
    for target_summary in target_summaries:
        max_gap = to_float(target_summary.get("max_revisit_gap_hours"))
        expected = to_float(target_summary.get("expected_revisit_period_hours"))
        if max_gap is None or expected is None:
            continue
        target_scores.append(
            revisit_target_gap_score(
                max_gap_hours=max_gap,
                expected_revisit_hours=expected,
                horizon_hours=horizon_hours,
                power=power,
            )
        )
    if not target_scores:
        return None
    return statistics.mean(target_scores)


def revisit_gap_score_pct_from_target_summaries(
    target_summaries: Iterable[Mapping[str, Any]],
    *,
    horizon_hours: float | int,
    power: float = DEFAULT_REVISIT_POWER,
) -> float | None:
    """Return the average target-level revisit gap score as percentage points."""
    score = revisit_gap_score_from_target_summaries(
        target_summaries,
        horizon_hours=horizon_hours,
        power=power,
    )
    return None if score is None else pct(score)


def revisit_constellation_score_pct(
    *,
    gap_score: float | int | None,
    num_satellites: float | int | None = None,
    min_satellites: float | int | None = None,
    max_satellites: float | int | None = None,
    gamma: float = DEFAULT_SCARCITY_GAMMA,
) -> float | None:
    """Compute the Revisit Constellation gated normalized score.

    Gap satisfaction fills the bottom 70 points. Only solutions that fully meet
    the gap target can receive the satellite-count scarcity bonus.
    """
    gap = to_float(gap_score)
    if gap is None:
        return None
    gap = clip01(gap)
    if gap < 1.0:
        return 70.0 * gap
    satellite_score = scarcity_bonus(
        num_satellites,
        n_min=min_satellites,
        n_max=max_satellites,
        gamma=gamma,
    )
    return 70.0 if satellite_score is None else 70.0 + 30.0 * satellite_score


def satnet_score_pct(
    *,
    u_rms: float | int | None,
    u_max: float | int | None,
    u_rms_cap: float | int | None,
    u_max_cap: float | int | None,
) -> float | None:
    """Compute the SatNet normalized score from u_rms and u_max residuals."""
    rms_score = lower_score(u_rms, u_rms_cap)
    max_score = lower_score(u_max, u_max_cap)
    if rms_score is None or max_score is None:
        return None
    return pct(0.75 * rms_score + 0.25 * max_score)


def spot5_score_pct(
    *,
    computed_profit: float | int | None,
    total_possible_profit: float | int | None,
    clip: bool = True,
) -> float | None:
    """Compute the SPOT5 normalized profit score.

    The denominator is a heuristic half of the unconstrained total profit, since
    the full sum is usually an unrealistic upper bound under SPOT5 conflicts
    and capacity constraints.

    Set clip=False when preserving over-baseline performance in legacy reports
    or diagnostic plots.
    """
    total_profit_float = to_float(total_possible_profit)
    if total_profit_float is None:
        return None
    return ratio_score_pct(computed_profit, 0.5 * total_profit_float, clip=clip)


def stereo_imaging_score_pct(*, normalized_quality: float | int | None) -> float | None:
    """Compute the Stereo Imaging normalized score from normalized quality."""
    normalized = to_float(normalized_quality)
    return None if normalized is None else pct(clip01(normalized))
