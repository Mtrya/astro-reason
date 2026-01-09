#!/usr/bin/env python3
"""Run all baselines on all benchmarks and log metrics.

Usage:
    python src/benchmark/run_baseline.py

    # Run all benchmarks explicitly
    python src/benchmark/run_baseline.py --benchmark all

    # Run specific benchmark
    python src/benchmark/run_baseline.py --benchmark revisit-optimization

    # Run all baselines explicitly
    python src/benchmark/run_baseline.py --baseline all

    # Run specific baselines (comma-separated)
    python src/benchmark/run_baseline.py --baseline greedy,simulated_annealing

    # Run all cases explicitly
    python src/benchmark/run_baseline.py --case all

    # Run specific cases (comma-separated)
    python src/benchmark/run_baseline.py --case case_0001,case_0002,case_0003
"""

import argparse
import sys
import json
import time
import importlib
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from benchmark.baselines import greedy_baseline, simulated_annealing

BENCHMARKS = [
    "revisit-optimization",
    "stereo-imaging",
    "latency-optimization",
    "regional-coverage",
]

BASELINES = {
    "greedy": greedy_baseline,
    "simulated_annealing": simulated_annealing,
}

TIMEOUTS = {
    "greedy": 600,
    "simulated_annealing": 600,
}


def get_cases(benchmark: str) -> List[str]:
    """Get list of case IDs for a benchmark."""
    benchmark_slug = benchmark.replace("-", "_")
    cases_dir = PROJECT_ROOT / "src" / "dataset" / benchmark_slug / "cases"
    
    if not cases_dir.exists():
        return []
        
    cases = sorted([d.name for d in cases_dir.iterdir() if d.is_dir() and d.name.startswith("case_")])
    return cases


def score_result(benchmark: str, case_id: str, plan_path: Path) -> dict[str, Any]:
    """Score the plan using the benchmark-specific verifier."""
    benchmark_slug = benchmark.replace("-", "_")
    verifier_module = f"benchmark.scenarios.{benchmark_slug}.verifier"
    case_dir = PROJECT_ROOT / "src" / "dataset" / benchmark_slug / "cases" / case_id
    
    try:
        verifier = importlib.import_module(verifier_module)
        score = verifier.score_plan(
            plan_path=str(plan_path),
            case_dir=str(case_dir),
        )
        return {"valid": True, "score": score}
    except Exception as e:
        return {"valid": False, "error": f"Verifier failed: {str(e)}"}


def extract_key_metrics(benchmark: str, score_data: dict) -> dict[str, Any]:
    """Extract benchmark-specific key metrics from verifier output."""
    if not score_data.get("valid"):
        return {"error": score_data.get("error", "Unknown error")}
    
    metrics = score_data.get("score", {}).get("metrics", {})
    
    if benchmark == "revisit-optimization":
        gap_stats = metrics.get("gap_statistics", {})
        max_gaps = [t["max_gap_hours"] for t in gap_stats.values() if t]
        avg_gaps = [t["avg_gap_hours"] for t in gap_stats.values() if t]

        return {
            "target_coverage_ratio": metrics.get("target_coverage", 0.0),
            "avg_avg_gap_hours" : sum(avg_gaps) / len(avg_gaps) if avg_gaps else None,
            "avg_max_gap_hours": sum(max_gaps) / len(max_gaps) if max_gaps else None,
        }
    
    elif benchmark == "stereo-imaging":
        return {
            "stereo_coverage_ratio": metrics.get("stereo_coverage", 0.0),
        }
    
    elif benchmark == "latency-optimization":
        latency_stats = metrics.get("latency_statistics", {})
        mean_latencies = [s["latency_mean_ms"] for s in latency_stats.values() if s and s.get("latency_mean_ms") is not None]
        max_latencies = [s["latency_max_ms"] for s in latency_stats.values() if s and s.get("latency_max_ms") is not None]
        
        return {
            "target_coverage_ratio": metrics.get("target_coverage", 0.0),
            "connection_coverage": metrics.get("connection_coverage", 0.0),
            "avg_max_latency_ms":  sum(max_latencies) / len(max_latencies) if max_latencies else None,
            "avg_mean_latency_ms": sum(mean_latencies) / len(mean_latencies) if mean_latencies else None,
        }
    
    elif benchmark == "regional-coverage":
        polygon_coverage = metrics.get("polygon_coverage", {})
        coverages = [p["coverage_percentage"] for p in polygon_coverage.values()]
        
        return {
            "mean_coverage_ratio": sum(coverages) / len(coverages) / 100.0 if coverages else 0.0,
        }
    
    return {}


def run_all(filter_benchmark=None, filter_baseline=None, filter_case=None):
    """Run all benchmarks and baselines."""

    benchmarks = BENCHMARKS if (filter_benchmark is None or filter_benchmark == "all") else [filter_benchmark]

    # Parse baseline list (comma-separated or single)
    if filter_baseline is None or filter_baseline == "all":
        baselines = list(BASELINES.keys())
    else:
        baselines = [b.strip() for b in filter_baseline.split(",")]
        # Validate baseline names
        invalid_baselines = [b for b in baselines if b not in BASELINES]
        if invalid_baselines:
            print(f"Error: Invalid baseline(s): {', '.join(invalid_baselines)}")
            print(f"Valid baselines: {', '.join(BASELINES.keys())}")
            return

    for benchmark in benchmarks:
        print(f"\n{'='*60}")
        print(f"Benchmark: {benchmark}")
        print(f"{'='*60}")

        all_cases = get_cases(benchmark)

        # Parse case list (comma-separated or single)
        if filter_case is None or filter_case == "all":
            cases = all_cases
        else:
            requested_cases = [c.strip() for c in filter_case.split(",")]
            cases = [c for c in requested_cases if c in all_cases]
            invalid_cases = [c for c in requested_cases if c not in all_cases]
            if invalid_cases:
                print(f"Warning: Case(s) not found: {', '.join(invalid_cases)}")
            if not cases:
                print(f"No valid cases found for {benchmark}")
                continue
        
        if not cases:
            print(f"No cases found for {benchmark}")
            continue

        metrics_file = PROJECT_ROOT / f"{benchmark.split('-')[0]}_metrics.txt"
        
        for case_id in cases:
            print(f"\nCase: {case_id}")
            case_slug = benchmark.replace("-", "_")
            case_path = PROJECT_ROOT / "src" / "dataset" / case_slug / "cases" / case_id
            
            for baseline_name in baselines:
                baseline_module = BASELINES[baseline_name]
                print(f"  Baseline: {baseline_name}...", end=" ", flush=True)
                
                output_dir = PROJECT_ROOT / "benchmark_runs" / f"baseline_{baseline_name}" / benchmark / case_id
                output_dir.mkdir(parents=True, exist_ok=True)
                plan_path = output_dir / "plan.json"
                
                start_time = time.time()
                try:
                    result = baseline_module.run(
                        case_path=case_path,
                        output_path=plan_path,
                        timeout=TIMEOUTS[baseline_name],
                        benchmark_type=case_slug,
                    )
                    
                    if result.success:
                        score = score_result(benchmark, case_id, plan_path)
                        key_metrics = extract_key_metrics(benchmark, score)
                        
                        elapsed = time.time() - start_time
                        print(f"Done ({elapsed:.1f}s) - Valid: {score['valid']}")
                        
                        # Log to metrics file
                        with open(metrics_file, "a") as f:
                            timestamp = datetime.now().astimezone().isoformat()
                            f.write(f"[{timestamp}] Case: {case_id}, Baseline: {baseline_name}\n")
                            f.write(f"Valid: {score.get('valid', False)}\n")
                            f.write(f"Run time: {result.elapsed_seconds:.2f}s\n")
                            
                            if key_metrics.get("error"):
                                f.write(f"Error: {key_metrics['error']}\n")
                            else:
                                for k, v in key_metrics.items():
                                    if v is not None:
                                        f.write(f"{k}: {v}\n")
                            f.write("-" * 60 + "\n")
                            
                    else:
                        print(f"Failed: {result.error}")
                        with open(metrics_file, "a") as f:
                            timestamp = datetime.now().astimezone().isoformat()
                            f.write(f"[{timestamp}] Case: {case_id}, Baseline: {baseline_name}\n")
                            f.write(f"Valid: False\n")
                            f.write(f"Error: {result.error}\n")
                            f.write("-" * 60 + "\n")
                            
                except Exception as e:
                    print(f"Error: {e}")
                    with open(metrics_file, "a") as f:
                        timestamp = datetime.now().astimezone().isoformat()
                        f.write(f"[{timestamp}] Case: {case_id}, Baseline: {baseline_name}\n")
                        f.write(f"Valid: False\n")
                        f.write(f"Exception: {str(e)}\n")
                        f.write("-" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run baselines")
    parser.add_argument("--benchmark", choices=["all"] + BENCHMARKS, help="Run specific benchmark or 'all' for all benchmarks")
    parser.add_argument("--baseline", help="Run specific baseline(s) (comma-separated), or 'all' for all baselines")
    parser.add_argument("--case", help="Run specific case ID(s) (comma-separated), or 'all' for all cases")

    args = parser.parse_args()

    run_all(args.benchmark, args.baseline, args.case)
