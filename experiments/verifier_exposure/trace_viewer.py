#!/usr/bin/env python3
"""Generate a static chatbot-style trace viewer for verifier exposure runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aggregate as family_aggregate  # type: ignore[no-redef]
else:
    from . import aggregate as family_aggregate

from experiments._shared import trace_viewer as shared_trace

FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "default.yaml"
DEFAULT_OUTPUT_DIR = FAMILY_DIR / "reports" / "traces"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a static trace viewer for verifier exposure session logs."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Config whose runs should be included.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where trace viewer files should be written.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=shared_trace.PREVIEW_CHARS,
        help="Visible preview characters per event.",
    )
    parser.add_argument(
        "--expanded-chars",
        type=int,
        default=shared_trace.EXPANDED_CHARS,
        help="Maximum expanded text characters per event.",
    )
    return parser.parse_args(argv)


def _relative_display(path: Path) -> str:
    return shared_trace._relative_display(path, family_aggregate.REPO_ROOT)


def _run_payload(
    *,
    exposure: str,
    benchmark: str,
    harness: str,
    split: str,
    case_id: str,
    output_dir: Path,
    run_data: dict[str, Any],
) -> dict[str, Any]:
    verifier = run_data.get("verifier")
    verifier = verifier if isinstance(verifier, dict) else {}
    run_id = shared_trace._safe_run_id((exposure, benchmark, harness, split, case_id))
    return {
        "id": run_id,
        "benchmark": benchmark,
        "harness": harness,
        "split": split,
        "exposure": exposure,
        "case_id": f"{exposure}/{case_id}",
        "raw_case_id": case_id,
        "overall_status": run_data.get("overall_status", "unknown"),
        "agent_status": run_data.get("agent_status", "unknown"),
        "verifier_status": run_data.get("verifier_status", "unknown"),
        "valid": verifier.get("valid"),
        "duration_seconds": run_data.get("duration_seconds"),
        "metrics": shared_trace._metric_summary(verifier),
        "result_path": _relative_display(output_dir),
        "data_file": f"data/events/{run_id}.js",
    }


def _config_list(config: dict[str, Any], key: str) -> tuple[str, ...]:
    values = config.get(key, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise SystemExit(f"Config {key} must be a list of strings.")
    return tuple(values)


def _build_trace_viewer(
    *,
    config_path: Path,
    output_dir: Path,
    preview_chars: int,
    expanded_chars: int,
) -> tuple[int, int]:
    config_path = config_path.resolve()
    config = family_aggregate._load_config(config_path)
    root = family_aggregate._result_root(config, config_path)
    config_name = config_path.stem

    runs: list[dict[str, Any]] = []
    events_by_run: dict[str, list[dict[str, Any]]] = {}
    for benchmark, split, case_ids in family_aggregate._benchmark_selections(config, config_path):
        for exposure in _config_list(config, "exposures"):
            for harness in _config_list(config, "harnesses"):
                for case_id in case_ids:
                    run_json = family_aggregate._run_path(
                        root,
                        config_name,
                        exposure=exposure,
                        benchmark=benchmark,
                        harness=harness,
                        split=split,
                        case_id=case_id,
                    )
                    if not run_json.exists():
                        continue
                    run_data = shared_trace._read_json(run_json)
                    if run_data is None:
                        continue
                    output = run_json.parent
                    run = _run_payload(
                        exposure=exposure,
                        benchmark=benchmark,
                        harness=harness,
                        split=split,
                        case_id=case_id,
                        output_dir=output,
                        run_data=run_data,
                    )
                    trace_source = shared_trace._find_trace_source(output, harness)
                    events: list[dict[str, Any]] = []
                    todos: list[dict[str, Any]] = []
                    if trace_source is not None:
                        events, todos = shared_trace._load_trace_events(
                            trace_source,
                            preview_chars=preview_chars,
                            expanded_chars=expanded_chars,
                        )
                        run["trace_source"] = _relative_display(trace_source.path)
                        run["trace_kind"] = trace_source.kind
                    else:
                        run["trace_source"] = None
                        run["trace_kind"] = None
                    run.update(shared_trace._event_summary(events, todos))
                    run["event_count"] = len(events)
                    runs.append(run)
                    events_by_run[run["id"]] = events

    output_dir.mkdir(parents=True, exist_ok=True)
    shared_trace._write_index_html(output_dir)
    shared_trace._write_trace_data(output_dir, runs, events_by_run)
    return len(runs), sum(len(events) for events in events_by_run.values())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_count, event_count = _build_trace_viewer(
        config_path=args.config,
        output_dir=args.output_dir,
        preview_chars=args.preview_chars,
        expanded_chars=args.expanded_chars,
    )
    print(f"Wrote trace viewer to {args.output_dir} ({run_count} runs, {event_count} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
