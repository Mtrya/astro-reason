"""CLI entry point for the relay_constellation verifier."""

from __future__ import annotations

import argparse

from .engine import verify_solution


def main(argv: list[str] | None = None) -> int:
    """
    CLI entry point that verifies a relay_constellation solution for a single case directory.
    
    Parses two positional command-line arguments (case directory and solution JSON), calls verify_solution with them, prints the verification result, and returns a process exit code.
    
    Parameters:
        argv (list[str] | None): Command-line arguments to parse; when None, uses the process's arguments.
    
    Returns:
        int: Exit code `0` if the verification result is valid, `1` otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Verify a relay_constellation solution against one case directory."
    )
    parser.add_argument(
        "case_dir",
        help="Path to dataset/cases/<case_id>",
    )
    parser.add_argument(
        "solution_path",
        help="Path to the solver-produced solution JSON file",
    )
    args = parser.parse_args(argv)

    result = verify_solution(args.case_dir, args.solution_path)
    print(result)
    return 0 if result.valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
