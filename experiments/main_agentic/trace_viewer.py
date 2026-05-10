#!/usr/bin/env python3
"""Generate a static chatbot-style trace viewer for main-agentic runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import plan as family_plan  # type: ignore[no-redef]
else:
    from . import plan as family_plan

from experiments._shared import trace_viewer as shared_trace


FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_OUTPUT_DIR = FAMILY_DIR / "reports" / "traces"

TraceSource = shared_trace.TraceSource
_event = shared_trace._event
_extract_claude_code_events = shared_trace._extract_claude_code_events
_extract_codex_events = shared_trace._extract_codex_events
_extract_kimi_events = shared_trace._extract_kimi_events
_extract_opencode_events = shared_trace._extract_opencode_events
_find_trace_source = shared_trace._find_trace_source
_latest_kimi_context = shared_trace._latest_kimi_context
_load_trace_events = shared_trace._load_trace_events
_safe_run_id = shared_trace._safe_run_id
_write_index_html = shared_trace._write_index_html
_write_trace_data = shared_trace._write_trace_data


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a static trace viewer for main-agentic session logs."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Batch config whose runs should be included.",
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
    return shared_trace._relative_display(path, family_plan.REPO_ROOT)


def _run_payload(item: family_plan.RunItem, output_dir: Path, run_data: dict[str, Any]) -> dict[str, Any]:
    verifier = run_data.get("verifier")
    verifier = verifier if isinstance(verifier, dict) else {}
    run_id = _safe_run_id((item.benchmark, item.harness, item.split, item.case_id))
    return {
        "id": run_id,
        "benchmark": item.benchmark,
        "harness": item.harness,
        "split": item.split,
        "case_id": item.case_id,
        "overall_status": run_data.get("overall_status", "unknown"),
        "agent_status": run_data.get("agent_status", "unknown"),
        "verifier_status": run_data.get("verifier_status", "unknown"),
        "valid": verifier.get("valid"),
        "duration_seconds": run_data.get("duration_seconds"),
        "metrics": shared_trace._metric_summary(verifier),
        "result_path": _relative_display(output_dir),
        "data_file": f"data/events/{run_id}.js",
    }


def _build_trace_viewer(
    *,
    config_path: Path,
    output_dir: Path,
    preview_chars: int,
    expanded_chars: int,
) -> tuple[int, int]:
    batch_plan = family_plan.build_batch_plan(
        config_path=config_path.resolve(),
        benchmark_filters=(),
        harness_filters=(),
        require_real_configs=False,
    )
    runs: list[dict[str, Any]] = []
    events_by_run: dict[str, list[dict[str, Any]]] = {}
    for item in batch_plan.items:
        output = family_plan.run_output_dir(item)
        run_json = output / "run.json"
        if not run_json.exists():
            continue
        run_data = shared_trace._read_json(run_json)
        if run_data is None:
            continue
        run = _run_payload(item, output, run_data)
        trace_source = _find_trace_source(output, item.harness)
        events: list[dict[str, Any]] = []
        todos: list[dict[str, Any]] = []
        if trace_source is not None:
            events, todos = _load_trace_events(
                trace_source,
                preview_chars=preview_chars,
                expanded_chars=expanded_chars,
            )
            run["trace_source"] = _relative_display(trace_source.path)
            run["trace_kind"] = trace_source.kind
        else:
            run["trace_source"] = None
            run["trace_kind"] = None
        summary = shared_trace._event_summary(events, todos)
        run.update(summary)
        run["event_count"] = len(events)
        runs.append(run)
        events_by_run[run["id"]] = events

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_index_html(output_dir)
    _write_trace_data(output_dir, runs, events_by_run)
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
