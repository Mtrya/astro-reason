# SPOT-5 Satellite Photography Scheduling Benchmark

A canonical constraint optimization problem for Earth observation satellite scheduling, originating from the ROADEF 2003 Challenge and the operations of the French Space Agency (CNES).

## Problem Overview

The SPOT-5 satellite (operational 2002-2015) carried three imaging instruments: two HRG (High-Resolution Geometric) cameras and one HRS (High-Resolution Stereoscopic) camera. The daily scheduling problem requires selecting photographs to maximize total profit while respecting:

- **Camera constraints**: mono images use one camera (HRG front, middle, or rear); stereo images require both HRG cameras simultaneously
- **Non-overlapping constraints**: photographs cannot conflict due to mirror slewing time limitations
- **Data flow constraints**: instantaneous telemetry bandwidth limitations prohibit certain combinations
- **Memory constraints**: on-board recording capacity limits total selected images (for multi-orbit instances)

This maps to a Disjunctively Constrained Knapsack Problem (DCKP) with complex logical constraints.

## Historical Context & Provenance

| Year | Event |
|------|-------|
| 2002 | SPOT-5 satellite launched by CNES |
| 2003 | ROADEF 2003 Challenge released raw telemetry data (multi-file format with orbital parameters) |
| 2001-2003 | Vasquez & Hao abstract physical constraints into conflict graphs (VCSP formulation) |
| 2021 | Wei & Hao further simplified and published 21 benchmark instances on Mendeley Data as DCKP format |

The current dataset (`.spot` files) is the DCKP abstraction hosted on [Mendeley Data](https://data.mendeley.com/datasets/2kbzg9nw3b/1) under **CC BY 4.0**. This license is permissive—not viral—because the abstraction process created a derived dataset separate from CNES's proprietary raw telemetry.

## Instance File Format (.spot)

### Overall Structure

```
<total_variables>
<variable_spec_lines...>
<total_constraints>
<constraint_spec_lines...>
[<capacity>]  # Optional, only for multi-orbit instances
```

### Variable Specification

Each variable represents a photograph request:

```
<var_id> <profit> <domain_size> {<value_id> <recorder_consumption>}* <domain_size> [extra_fields...]
```

- **var_id**: Variable identifier (0-indexed)
- **profit**: Weight/profit gained if selected (objective to maximize)
- **domain_size**: Number of possible camera assignments (always 3 for SPOT-5)
- **value_id**, **recorder_consumption**: Pairs defining allowed values
  - Value `1`: HRG front camera
  - Value `2`: HRS middle camera  
  - Value `3`: HRG rear camera
  - Value `13`: HRG front + rear cameras
- **extra_fields**: Not sure, ignored 

For 14 single-orbit instances: all `recorder_consumption = 0`
For 7 multi-orbit instances: `recorder_consumption` indicates memory usage

Examples:

1. single-orbit, domain_size = 3

```11.spot, line 3
1 1 3 1 0 2 0 3 0
```

1 -> var_id (the second variable)
1 -> profit (one point of profit gained if selected)
3 -> domain_size: 3 possible camera assignments (which is 1, 2, 3)
1 0 -> value_id 1, recorder_consumption 0
2 0 -> value_id 2, recorder_consumption 0
3 0 -> value_id 3, recorder_consumption 0

2. multi-orbit, domain_size = 3

```1504.spot, line 40
38 2 3 1 451.1500000000069 2 451.1500000000069 3 451.1500000000069 213302 1
```

38 -> var_id (the 39th variable)
2 -> profit (two points of profit gained if selected)
3 -> domain_size: 3 possible camera assignments (which is 1, 2, 3)
1 451.1500000000069 -> value_id 1, recorder_consumption 451.1500000000069
2 451.1500000000069 -> value_id 2, recorder_consumption 451.1500000000069
3 451.1500000000069 -> value_id 3, recorder_consumption 451.1500000000069
213302 1 -> extra_field, ignored

3. multi-orbit, domain_size = 1

```1506.spot, line 127
125 2000 1 13 1804.5999999999822 136703 1
```

125 -> var_id (the 126th variable)
2000 -> profit (two thousand points of profit gained if selected)
1 -> domain_size: 1 possible camera assignment (which is 13)
13 1804.5999999999822 -> value_id 13, recorder_consumption 1804.5999999999822
136703 1 -> extra_field, ignored

### Constraint Specification

```
<arity> <var_id_1> ... <var_id_arity> {<forbidden_tuple>}*
```

- **arity**: Number of variables (2 = binary, 3 = ternary)
- **var_id_***: Variables involved in constraint
- **forbidden_tuple**: Forbidden value combinations (space-separated)

**Binary constraints** encode disjunctive conflicts: two photographs cannot both be selected. Forbidden tuples are value pairs (e.g., `1 1 2 2 3 3` means "cannot both use camera 1, or both use camera 2, or both use camera 3").

**Ternary constraints** encode data flow limitations or complex interference patterns. Forbidden tuples are value triples.

Examples:

1. binary

```11.spot, line 370
2 242 240 13 3 13 1
```

2 -> arity (binary)
242 -> var_id_1
240 -> var_id_2
13 3 -> forbidden_tuple 1
13 1 -> forbidden_tuple 2

It's forbidden to assign value 13 to variable 242 AND assign value 3 to variable 240 at the same time; It's forbidden to assign value 13 to variable 242 AND value 1 to variable 240 at the same time

2. ternary

```11.spot, line 369
3 124 81 72 13 2 13
```

3 -> arity (ternary)
124 -> var_id_1
81 -> var_id_2
72 -> var_id_3
13 2 13 -> forbidden_tuple 1

It's forbidden to assign value 13 to variable 124 AND assign value 2 to variable 81 AND assign value 13 to variable 72 at the same time


### Capacity Line (Multi-orbit only)

For instances `1401, 1403, 1405, 1502, 1504, 1506, 1021`, the file ends with a single number representing the memory capacity constraint. **Important**: This number in the file is ignored in the verifier. The true capacity is always **200**.

## Solution File Format (.spot_sol.txt)

```
profit = <P>, weight = <W>
number of candidate photographs = <N>
number of selected photographs = <S>
<assignment_0>
<assignment_1>
...
<assignment_n-1>
```

- **P**: Total profit (sum of weights of selected photographs)
- **W**: Total memory used (for multi-orbit instances, see Weight Calculation)
- **N**: Total number of candidate photographs (variables)
- **S**: Number of selected photographs (assignments ≠ 0)
- **assignments**: One per variable, values from `{0, 1, 2, 3}`

## Constraint Types Validation

A solution is valid if it satisfies all constraints:

### Binary Constraints
For each binary constraint `C(i, j)` with forbidden tuples `F`:
- If `assignment[i] ≠ 0` AND `assignment[j] ≠ 0`: the pair `(assignment[i], assignment[j])` must NOT be in `F`
- If either is 0: constraint satisfied

### Ternary Constraints
For each ternary constraint `C(i, j, k)` with forbidden tuples `F`:
- If all three assignments ≠ 0: the triple must NOT be in `F`
- If any is 0: constraint satisfied

### Memory Capacity Constraint (Multi-orbit only)
```
total_weight ≤ 200
```

Where `total_weight` is calculated per Weight Calculation below.

## Score Calculation

### Profit
```python
profit = sum(variables[i].profit for i in range(n) if assignment[i] != 0)
```

### Weight (Memory Usage)

**Single-orbit instances** (8, 54, 404, 408, 412, 5, 11, 28, 29, 42, 503, 505, 507, 509):
- All memory consumptions are 0
- `weight = 0`

**Multi-orbit instances** (1401, 1403, 1405, 1502, 1504, 1506, 1021):

For each variable with domain values, the raw `recorder_consumption` values must be normalized:
```python
# Example from 1021.spot line:
# 0 1000 1 2 451.1500000000069 42510 1
# Value 1 has recorder_consumption = 451.1500000000069

weight_per_value = [round(recorder_consumption / 451) for recorder_consumption in variable.recorder_consumptions]

total_weight = sum(
    weight_per_value[assignment[i]]
    for i in range(n) if assignment[i] != 0
)
```

Constraint: `total_weight ≤ 200`

## Instance Classification

### Total: 21 Instances

| Category | Instances | Variables | Constraints | Capacity |
|----------|-----------|-----------|-------------|----------|
| Small (single-orbit) | 8, 54, 404, 408, 412 | 8-78 | 7-52 | 0 |
| Medium (single-orbit) | 5, 11, 28, 29, 42 | 306-309 | 4308-6273 | 0 |
| Large (single-orbit) | 503, 505, 507, 509 | 315 | 3983-8122 | 0 |
| Multi-orbit | 1401, 1403, 1405, 1502, 1504, 1506 | 163-855 | Variable | 200 |
| Multi-orbit (largest) | 1021 | 21,790 | High density | 200 |

**14 instances without memory constraint** (capacity = 0)
**7 instances with memory constraint** (capacity = 200)

## Known Solutions & Validation

Reference solutions are available in `tests/fixtures/spot5_val_sol/`, obtained from the [DCKP_RSOA repository](https://github.com/Zequn-Wei/DCKP_RSOA).

Validation results (using `verifier.py`):

- **14 solutions**: Perfect match between claimed and computed profits/weights
- **7 solutions**: Valid assignments but small discrepancies in reported header values

**Header mismatches** (assignments themselves are correct):

| Instance | Claimed Profit | Computed Profit | Diff | Weight Status |
|----------|----------------|-----------------|------|---------------|
| 11       | 22,117         | 22,119          | +2   | ✓ (0) |
| 408      | 3,078          | 3,080           | +2   | ✓ (0) |
| 509      | 19,115         | 19,117          | +2   | ✓ (0) |
| 1403     | 172,141        | 172,143         | +2   | ✓ (0) |
| 1506     | 164,239        | 164,241         | +2   | ✓ (0) |
| 1021     | 169,240        | 169,243         | +3   | Claimed 200, actual 198 |
| 1405     | 170,175        | 170,179         | +4   | Claimed 200, actual 198 |

The verifier treats these cases as **valid solutions**; the discrepancies appear to be in the DCKP-RSOA algorithm's profit/weight reporting logic, not in the solution quality.

## Verification Usage

```bash
# Verify a solution
python benchmarks/spot5/verifier.py \
    benchmarks/spot5/dataset/8.spot \
    tests/fixtures/spot5_val_sol/8.spot_sol.txt
```

The verifier checks:
1. All assignments are in valid domains
2. All binary constraints satisfied
3. All ternary constraints satisfied
4. Memory capacity constraint satisfied (if applicable)
5. Profit calculation matches
6. Weight calculation matches
7. Selected count matches header

## File Locations

- **Instance files**: `benchmarks/spot5/dataset/*.spot`
- **Solution files**: `tests/fixtures/spot5_val_sol/*.spot_sol.txt`
- **Verifier**: `benchmarks/spot5/verifier.py`

## License & Attribution

**Data License**: CC BY 4.0 (Creative Commons Attribution 4.0 International)
**Source**: Mendeley Data, DOI: 10.17632/2kbzg9nw3b.1
**Attribution**:
- Original problem: CNES (French Space Agency) & ONERA
- Problem abstraction: Vasquez & Hao (2001), Wei & Hao (2021)
- Reference solutions: DCKP-RSOA algorithm (Wei & Hao, 2021)

**Commercial Use**: Permitted under CC BY 4.0. The dataset is not virally licensed, unlike the solution program which uses GPL, the Mendeley Data release is permissive.

## References

1. Bensana E, Lemaitre M, Verfaillie G. "Earth observation satellite management." Constraints, 1999.
2. Verfaillie G, Lemaitre M, Schiex T. "Russian Doll Search for Solving Constraint Optimization Problems." AAAI-96, 1996.
3. Agnès J-C, Bataille N, Blumstein D, et al. "Exact and Approximate Methods for the Daily Management of an Earth Observation Satellite." ESA Workshop 1995.
4. Vasquez M, Hao JK. "A Logic-Constrained Knapsack Formulation and a Tabu Search Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite." 2001.
5. Wei Z, Hao JK. "A Threshold Search Based Memetic Algorithm for the Disjunctively Constrained Knapsack Problem." Applied Soft Computing, 2021.