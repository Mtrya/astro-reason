"""
SPOT-5 Satellite Photography Scheduling Benchmark Verifier

Verifies solutions for the SPOT-5 Disjunctively Constrained Knapsack Problem.
Based on the ROADEF 2003 Challenge dataset and Wei & Hao's DCKP formulation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Variable:
    """Represents a candidate photograph (variable) in the problem."""

    var_id: int
    profit: int
    domain: dict[int, float]  # value_id -> recorder_consumption

    def get_consumption(self, value: int) -> float:
        """Get recorder consumption for a given camera assignment."""
        return self.domain.get(value, 0.0)

    def is_valid_assignment(self, value: int) -> bool:
        """Check if a value is in this variable's domain (0 is always valid)."""
        return value == 0 or value in self.domain


@dataclass
class Constraint:
    """Represents a binary or ternary constraint with forbidden tuples."""

    arity: int
    variables: list[int]  # var_ids involved
    forbidden: set[tuple[int, ...]]  # set of forbidden value tuples


@dataclass
class Instance:
    """A complete SPOT-5 problem instance."""

    variables: list[Variable]
    constraints: list[Constraint]
    capacity: int  # 0 for single-orbit, 200 for multi-orbit (file value ignored)

    @property
    def is_multi_orbit(self) -> bool:
        return self.capacity > 0

    @property
    def n_variables(self) -> int:
        return len(self.variables)


@dataclass
class Solution:
    """A solution to a SPOT-5 problem instance."""

    claimed_profit: int
    claimed_weight: int
    n_candidates: int
    n_selected: int
    assignments: list[int]  # value for each variable (0 = not selected)


@dataclass
class VerificationResult:
    """Result of verifying a solution against an instance."""

    is_valid: bool
    computed_profit: int = 0
    computed_weight: int = 0
    computed_selected: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        lines = [f"Status: {status}"]
        lines.append(f"Computed Profit: {self.computed_profit}")
        lines.append(f"Computed Weight: {self.computed_weight}")
        lines.append(f"Selected Photos: {self.computed_selected}")
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


# Multi-orbit instance identifiers (these have capacity constraint)
MULTI_ORBIT_INSTANCES = {"1021", "1401", "1403", "1405", "1502", "1504", "1506"}

# Weight normalization divisor for multi-orbit instances
WEIGHT_DIVISOR = 451

# Fixed capacity for multi-orbit instances (file value is ignored)
FIXED_CAPACITY = 200


def parse_instance(filepath: str | Path) -> Instance:
    """
    Parse a .spot instance file.

    File format:
        <n_variables>
        <var_id> <profit> <domain_size> {<value_id> <consumption>}* [extra...]
        ...
        <n_constraints>
        <arity> {<var_id>}* {<forbidden_tuple_values>}*
        ...
        [<capacity>]  # optional, only for multi-orbit
    """
    filepath = Path(filepath)
    instance_name = filepath.stem

    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    idx = 0

    # Parse number of variables
    n_vars = int(lines[idx])
    idx += 1

    # Parse variables
    variables = []
    for i in range(n_vars):
        parts = lines[idx].split()
        idx += 1

        var_id = int(parts[0])
        profit = int(parts[1])
        domain_size = int(parts[2])

        # Parse (value_id, consumption) pairs
        domain = {}
        for j in range(domain_size):
            value_id = int(parts[3 + 2 * j])
            consumption = float(parts[4 + 2 * j])
            domain[value_id] = consumption

        variables.append(Variable(var_id=var_id, profit=profit, domain=domain))

    # Parse number of constraints
    n_constraints = int(lines[idx])
    idx += 1

    # Parse constraints
    constraints = []
    for _ in range(n_constraints):
        parts = lines[idx].split()
        
        # Check if this is the capacity line (single number, typically large)
        # A constraint line always starts with arity (2 or 3) and has more fields
        if len(parts) == 1:
            # This is the capacity line, not a constraint
            break
            
        idx += 1

        arity = int(parts[0])
        var_ids = [int(parts[1 + i]) for i in range(arity)]

        # Remaining values are forbidden tuples (groups of `arity` values)
        tuple_values = [int(x) for x in parts[1 + arity :]]
        forbidden = set()
        for i in range(0, len(tuple_values), arity):
            forbidden.add(tuple(tuple_values[i : i + arity]))

        constraints.append(
            Constraint(arity=arity, variables=var_ids, forbidden=forbidden)
        )

    # Determine capacity (multi-orbit instances have capacity = 200)
    # Note: The capacity in the file is ignored; we use FIXED_CAPACITY
    capacity = FIXED_CAPACITY if instance_name in MULTI_ORBIT_INSTANCES else 0

    return Instance(variables=variables, constraints=constraints, capacity=capacity)


def parse_solution(filepath: str | Path) -> Solution:
    """
    Parse a .spot_sol.txt solution file.

    File format:
        profit = <P>, weight = <W>
        number of candidate photographs = <N>
        number of selected photographs = <S>
        <assignment_0>
        <assignment_1>
        ...
    """
    filepath = Path(filepath)

    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Parse header line 1: "profit = X, weight = Y"
    header1 = lines[0]
    profit_part, weight_part = header1.split(",")
    claimed_profit = int(profit_part.split("=")[1].strip())
    claimed_weight = int(weight_part.split("=")[1].strip())

    # Parse header line 2: "number of candidate photographs = N"
    n_candidates = int(lines[1].split("=")[1].strip())

    # Parse header line 3: "number of selected photographs = S"
    n_selected = int(lines[2].split("=")[1].strip())

    # Parse assignments (one per line)
    assignments = []
    for i in range(3, 3 + n_candidates):
        assignments.append(int(lines[i]))

    return Solution(
        claimed_profit=claimed_profit,
        claimed_weight=claimed_weight,
        n_candidates=n_candidates,
        n_selected=n_selected,
        assignments=assignments,
    )


def verify(instance: Instance, solution: Solution) -> VerificationResult:
    """
    Verify a solution against an instance.

    Checks:
    1. Assignment count matches
    2. Each assignment is within the variable's domain
    3. All binary constraints satisfied
    4. All ternary constraints satisfied
    5. Capacity constraint satisfied (multi-orbit only)
    """
    errors = []
    warnings = []

    # Check assignment count matches number of variables
    if len(solution.assignments) != instance.n_variables:
        errors.append(
            f"Assignment count mismatch: got {len(solution.assignments)}, "
            f"expected {instance.n_variables}"
        )
        return VerificationResult(is_valid=False, errors=errors)

    # Check n_candidates matches
    if solution.n_candidates != instance.n_variables:
        warnings.append(
            f"Candidate count in header ({solution.n_candidates}) "
            f"differs from instance ({instance.n_variables})"
        )

    # Step 1: Check domain validity
    for i, val in enumerate(solution.assignments):
        var = instance.variables[i]
        if not var.is_valid_assignment(val):
            errors.append(
                f"Variable {i}: assignment {val} not in domain {set(var.domain.keys())}"
            )

    if errors:
        return VerificationResult(is_valid=False, errors=errors, warnings=warnings)

    # Step 2: Check binary and ternary constraints
    for constraint in instance.constraints:
        var_ids = constraint.variables
        values = [solution.assignments[v] for v in var_ids]

        # Constraint is satisfied if any variable is 0 (not selected)
        if any(v == 0 for v in values):
            continue

        # Check if assignment matches a forbidden tuple
        assignment_tuple = tuple(values)
        if assignment_tuple in constraint.forbidden:
            if constraint.arity == 2:
                errors.append(
                    f"Binary constraint violated: variables {var_ids} "
                    f"assigned {values}, which is forbidden"
                )
            else:
                errors.append(
                    f"Ternary constraint violated: variables {var_ids} "
                    f"assigned {values}, which is forbidden"
                )

    if errors:
        return VerificationResult(is_valid=False, errors=errors, warnings=warnings)

    # Step 3: Calculate profit
    computed_profit = sum(
        instance.variables[i].profit
        for i, val in enumerate(solution.assignments)
        if val != 0
    )

    # Step 4: Calculate weight (for multi-orbit instances)
    computed_weight = 0
    if instance.is_multi_orbit:
        for i, val in enumerate(solution.assignments):
            if val != 0:
                consumption = instance.variables[i].get_consumption(val)
                normalized = round(consumption / WEIGHT_DIVISOR)
                computed_weight += normalized

        # Check capacity constraint
        if computed_weight > FIXED_CAPACITY:
            errors.append(
                f"Capacity exceeded: weight {computed_weight} > {FIXED_CAPACITY}"
            )
            return VerificationResult(
                is_valid=False,
                computed_profit=computed_profit,
                computed_weight=computed_weight,
                errors=errors,
                warnings=warnings,
            )

    # Step 5: Count selected photos
    computed_selected = sum(1 for val in solution.assignments if val != 0)

    # Add warnings for mismatches in header values
    if computed_profit != solution.claimed_profit:
        warnings.append(
            f"Profit mismatch: computed {computed_profit}, "
            f"claimed {solution.claimed_profit}"
        )

    if computed_weight != solution.claimed_weight:
        warnings.append(
            f"Weight mismatch: computed {computed_weight}, "
            f"claimed {solution.claimed_weight}"
        )

    if computed_selected != solution.n_selected:
        warnings.append(
            f"Selected count mismatch: computed {computed_selected}, "
            f"claimed {solution.n_selected}"
        )

    return VerificationResult(
        is_valid=True,
        computed_profit=computed_profit,
        computed_weight=computed_weight,
        computed_selected=computed_selected,
        errors=errors,
        warnings=warnings,
    )


def verify_files(
    instance_path: str | Path, solution_path: str | Path
) -> VerificationResult:
    """Convenience function to verify from file paths."""
    instance = parse_instance(instance_path)
    solution = parse_solution(solution_path)
    return verify(instance, solution)


def main():
    """Command-line interface for the verifier."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify SPOT-5 satellite scheduling solutions"
    )
    parser.add_argument("instance", help="Path to .spot instance file")
    parser.add_argument("solution", help="Path to .spot_sol.txt solution file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    result = verify_files(args.instance, args.solution)

    if args.verbose:
        print(result)
    else:
        status = "VALID" if result.is_valid else "INVALID"
        print(f"{status}: profit={result.computed_profit}, weight={result.computed_weight}")

    return 0 if result.is_valid else 1


if __name__ == "__main__":
    exit(main())
