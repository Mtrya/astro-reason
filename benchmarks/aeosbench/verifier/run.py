#!/usr/bin/env python3
"""Command-line entry point for AEOS-Bench verifier.

This script validates satellite constellation scheduling solutions against
case instances and computes performance metrics using the Basilisk astrodynamics
simulator.

Usage:
    python run.py <case_dir> <solution_path> [options]

Example:
    python run.py dataset/cases/00157 solutions/00157.json
    python run.py dataset/cases/00157 solutions/00157.json -v
    python run.py dataset/cases/00157 solutions/00157.json --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import AEOSVerifierBSK


def load_case(case_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load constellation and taskset from case directory.

    Args:
        case_dir: Path to case directory containing constellation.json and taskset.json

    Returns:
        Tuple of (constellation_dict, taskset_dict)
    """
    constellation_path = case_dir / "constellation.json"
    taskset_path = case_dir / "taskset.json"

    if not constellation_path.exists():
        raise FileNotFoundError(f"Constellation file not found: {constellation_path}")
    if not taskset_path.exists():
        raise FileNotFoundError(f"Taskset file not found: {taskset_path}")

    with open(constellation_path) as f:
        constellation = json.load(f)
    with open(taskset_path) as f:
        taskset = json.load(f)

    return constellation, taskset


def load_solution(solution_path: Path) -> dict[str, Any]:
    """Load solution from JSON file.

    Args:
        solution_path: Path to solution JSON file

    Returns:
        Solution dict with 'assignments' key
    """
    with open(solution_path) as f:
        solution = json.load(f)
    return solution


def verify(
    case_dir: Path,
    solution_path: Path,
) -> dict[str, Any]:
    """Verify a solution against a case.

    Args:
        case_dir: Path to case directory
        solution_path: Path to solution JSON file

    Returns:
        Dict with metrics and validity status
    """
    # Load case data
    constellation, taskset = load_case(case_dir)

    # Load solution
    solution = load_solution(solution_path)

    # Extract assignments
    assignments_raw = solution.get("assignments", {})

    # Convert assignments from dict of lists to dict of lists with int keys/values
    # Keys in JSON are strings, we need integers for satellite IDs
    assignments: dict[int, list[int]] = {}
    for sat_id_str, assignment_list in assignments_raw.items():
        sat_id = int(sat_id_str)
        assignments[sat_id] = [int(a) for a in assignment_list]

    # Run verifier
    verifier = AEOSVerifierBSK(constellation, taskset)
    result = verifier.verify(assignments)

    return result


def format_text_output(result: dict[str, Any]) -> str:
    """Format verification result as human-readable text.

    Args:
        result: Verification result dict

    Returns:
        Formatted string
    """
    lines = []

    # Status
    is_valid = result.get("valid", False)
    status = "VALID" if is_valid else "INVALID"
    lines.append(f"Status: {status}")

    # Metrics
    lines.append("")
    lines.append("Metrics:")
    lines.append(f"  CR (Completion Rate):          {result.get('CR', 0.0):.6f}")
    lines.append(f"  WCR (Weighted Completion Rate): {result.get('WCR', 0.0):.6f}")
    lines.append(f"  PCR (Partial Completion Rate):  {result.get('PCR', 0.0):.6f}")
    lines.append(f"  WPCR (Weighted Partial CR):     {result.get('WPCR', 0.0):.6f}")
    lines.append(f"  TAT (Turn-Around Time):        {result.get('TAT', 0.0):.2f} s")
    lines.append(f"  PC (Power Consumption):        {result.get('PC', 0.0):.2f} Ws")

    return "\n".join(lines)


def format_compact_output(result: dict[str, Any]) -> str:
    """Format verification result as compact text.

    Args:
        result: Verification result dict

    Returns:
        Single-line formatted string
    """
    is_valid = result.get("valid", False)
    status = "VALID" if is_valid else "INVALID"
    cr = result.get("CR", 0.0)
    wcr = result.get("WCR", 0.0)
    pcr = result.get("PCR", 0.0)
    wpcr = result.get("WPCR", 0.0)
    tat = result.get("TAT", 0.0)
    pc = result.get("PC", 0.0)

    return (
        f"{status}: CR={cr:.4f} WCR={wcr:.4f} PCR={pcr:.4f} "
        f"WPCR={wpcr:.4f} TAT={tat:.2f} PC={pc:.2f}"
    )


def main() -> int:
    """Command-line interface for the AEOS-Bench verifier.

    Returns:
        Exit code (0 for valid, 1 for invalid/error)
    """
    parser = argparse.ArgumentParser(
        description="Verify AEOS-Bench satellite scheduling solutions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s dataset/cases/00157 solutions/00157.json
  %(prog)s dataset/cases/00157 solutions/00157.json -v
  %(prog)s dataset/cases/00157 solutions/00157.json --format json
        """,
    )

    parser.add_argument(
        "case_dir",
        type=Path,
        help="Path to case directory containing constellation.json and taskset.json",
    )
    parser.add_argument(
        "solution",
        type=Path,
        help="Path to solution JSON file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output with detailed metrics",
    )
    parser.add_argument(
        "--format",
        choices=["text", "compact", "json"],
        default="compact",
        help="Output format (default: compact)",
    )

    args = parser.parse_args()

    try:
        result = verify(args.case_dir, args.solution)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Verification failed: {e}", file=sys.stderr)
        return 2

    # Output result
    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif args.format == "text" or args.verbose:
        print(format_text_output(result))
    else:  # compact
        print(format_compact_output(result))

    return 0 if result.get("valid", False) else 1


if __name__ == "__main__":
    sys.exit(main())
