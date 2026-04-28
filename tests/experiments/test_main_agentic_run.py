from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import plan, run


def _preview_item(harness: str, case_id: str = "case_0001") -> SimpleNamespace:
    return SimpleNamespace(
        action="run",
        existing_overall_status=None,
        artifact_state="missing",
        item=SimpleNamespace(
            benchmark="satnet",
            harness=harness,
            split="test",
            case_id=case_id,
        ),
    )


def test_next_ready_item_skips_cooling_harness_when_other_harness_is_ready() -> None:
    now = datetime(2026, 4, 28, tzinfo=timezone.utc)
    pending = [
        _preview_item("codex", "case_a"),
        _preview_item("gemini_cli", "case_b"),
        _preview_item("codex", "case_c"),
    ]

    ready_index = run._next_ready_item_index(
        pending,
        active_harnesses=set(),
        last_finish_by_harness={"codex": now},
        cooldown_seconds=30,
        now=now + timedelta(seconds=10),
    )

    assert ready_index == 1


def test_earliest_pending_ready_at_ignores_active_harnesses() -> None:
    now = datetime(2026, 4, 28, tzinfo=timezone.utc)
    ready_at = run._earliest_pending_ready_at(
        [_preview_item("codex"), _preview_item("gemini_cli")],
        active_harnesses={"gemini_cli"},
        last_finish_by_harness={"codex": now},
        cooldown_seconds=30,
        now=now + timedelta(seconds=10),
    )

    assert ready_at == now + timedelta(seconds=30)


def test_harness_cooldown_scheduler_waits_between_same_harness_runs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_now = [datetime(2026, 4, 28, tzinfo=timezone.utc)]
    starts: dict[str, datetime] = {}

    def fake_utc_now() -> datetime:
        return fake_now[0]

    def fake_sleep(seconds: float) -> None:
        fake_now[0] += timedelta(seconds=seconds)

    def fake_execute_run_item_attempt(
        preview_item: SimpleNamespace,
        *,
        timeout_override: int | None,
        attempt: int,
        attempts: int,
    ) -> run.RunExecutionResult:
        starts[preview_item.item.case_id] = fake_now[0]
        return run.RunExecutionResult(
            overall_status="success",
            skipped=False,
            output_dir=tmp_path / preview_item.item.case_id,
            exit_code=0,
        )

    monkeypatch.setattr(run, "_utc_now", fake_utc_now)
    monkeypatch.setattr(run.time, "sleep", fake_sleep)
    monkeypatch.setattr(run, "_execute_run_item_attempt", fake_execute_run_item_attempt)

    batch_settings = plan.BatchSettings(
        max_concurrency=2,
        max_retries=0,
        harness_cooldown_seconds=30,
        skip_completed=True,
        retry_statuses=(),
    )
    progress = run.BatchProgress(
        results=[],
        completed=0,
        executed_count=0,
        skipped_count=0,
        status_counts={},
    )

    run._run_runnable_items_with_harness_cooldown(
        runnable_items=(
            _preview_item("codex", "codex_first"),
            _preview_item("codex", "codex_second"),
            _preview_item("gemini_cli", "gemini_first"),
        ),
        batch_settings=batch_settings,
        timeout_override=None,
        max_workers=2,
        progress=progress,
        total_items=3,
    )

    assert starts["gemini_first"] == starts["codex_first"]
    assert starts["codex_second"] >= starts["codex_first"] + timedelta(seconds=30)
    assert progress.executed_count == 3
    assert progress.status_counts == {"success": 3}


def test_harness_cooldown_scheduler_measures_from_finish_time(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_now = [datetime(2026, 4, 28, tzinfo=timezone.utc)]
    starts: dict[str, datetime] = {}
    durations = {
        "codex_first": timedelta(seconds=7),
        "codex_second": timedelta(seconds=0),
    }

    def fake_utc_now() -> datetime:
        return fake_now[0]

    def fake_sleep(seconds: float) -> None:
        fake_now[0] += timedelta(seconds=seconds)

    def fake_execute_run_item_attempt(
        preview_item: SimpleNamespace,
        *,
        timeout_override: int | None,
        attempt: int,
        attempts: int,
    ) -> run.RunExecutionResult:
        starts[preview_item.item.case_id] = fake_now[0]
        fake_now[0] += durations[preview_item.item.case_id]
        return run.RunExecutionResult(
            overall_status="success",
            skipped=False,
            output_dir=tmp_path / preview_item.item.case_id,
            exit_code=0,
        )

    monkeypatch.setattr(run, "_utc_now", fake_utc_now)
    monkeypatch.setattr(run.time, "sleep", fake_sleep)
    monkeypatch.setattr(run, "_execute_run_item_attempt", fake_execute_run_item_attempt)

    batch_settings = plan.BatchSettings(
        max_concurrency=1,
        max_retries=0,
        harness_cooldown_seconds=30,
        skip_completed=True,
        retry_statuses=(),
    )
    progress = run.BatchProgress(
        results=[],
        completed=0,
        executed_count=0,
        skipped_count=0,
        status_counts={},
    )

    run._run_runnable_items_with_harness_cooldown(
        runnable_items=(
            _preview_item("codex", "codex_first"),
            _preview_item("codex", "codex_second"),
        ),
        batch_settings=batch_settings,
        timeout_override=None,
        max_workers=1,
        progress=progress,
        total_items=2,
    )

    assert starts["codex_second"] == (
        starts["codex_first"] + durations["codex_first"] + timedelta(seconds=30)
    )


def test_harness_cooldown_scheduler_applies_cooldown_between_retries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fake_now = [datetime(2026, 4, 28, tzinfo=timezone.utc)]
    starts: list[datetime] = []

    def fake_utc_now() -> datetime:
        return fake_now[0]

    def fake_sleep(seconds: float) -> None:
        fake_now[0] += timedelta(seconds=seconds)

    def fake_execute_run_item_attempt(
        preview_item: SimpleNamespace,
        *,
        timeout_override: int | None,
        attempt: int,
        attempts: int,
    ) -> run.RunExecutionResult:
        starts.append(fake_now[0])
        fake_now[0] += timedelta(seconds=7 if attempt == 1 else 0)
        return run.RunExecutionResult(
            overall_status="runner_error" if attempt == 1 else "success",
            skipped=False,
            output_dir=tmp_path / f"attempt_{attempt}",
            exit_code=0 if attempt == 2 else 1,
        )

    monkeypatch.setattr(run, "_utc_now", fake_utc_now)
    monkeypatch.setattr(run.time, "sleep", fake_sleep)
    monkeypatch.setattr(run, "_execute_run_item_attempt", fake_execute_run_item_attempt)

    batch_settings = plan.BatchSettings(
        max_concurrency=1,
        max_retries=1,
        harness_cooldown_seconds=30,
        skip_completed=True,
        retry_statuses=("runner_error",),
    )
    progress = run.BatchProgress(
        results=[],
        completed=0,
        executed_count=0,
        skipped_count=0,
        status_counts={},
    )

    run._run_runnable_items_with_harness_cooldown(
        runnable_items=(_preview_item("codex", "codex_retry"),),
        batch_settings=batch_settings,
        timeout_override=None,
        max_workers=1,
        progress=progress,
        total_items=1,
    )

    assert starts[1] == starts[0] + timedelta(seconds=37)
    assert progress.executed_count == 1
    assert progress.status_counts == {"success": 1}


def test_run_batch_preserves_upfront_submission_when_cooldown_is_zero(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preview_item = _preview_item("codex", "case_0001")
    batch_settings = plan.BatchSettings(
        max_concurrency=2,
        max_retries=0,
        harness_cooldown_seconds=0,
        skip_completed=True,
        retry_statuses=(),
    )
    preview = SimpleNamespace(
        items=(preview_item,),
        plan=SimpleNamespace(config=SimpleNamespace(batch=batch_settings)),
    )
    calls: list[str] = []

    def fake_run_upfront(
        *,
        runnable_items: tuple[SimpleNamespace, ...],
        batch_settings: plan.BatchSettings,
        timeout_override: int | None,
        max_workers: int,
        progress: run.BatchProgress,
        total_items: int,
    ) -> None:
        calls.append("upfront")
        run._record_batch_result(
            progress=progress,
            total_items=total_items,
            preview_item=runnable_items[0],
            result=run.RunExecutionResult(
                overall_status="success",
                skipped=False,
                output_dir=tmp_path / "case_0001",
                exit_code=0,
            ),
        )

    def fail_cooldown_scheduler(**kwargs: object) -> None:
        raise AssertionError("cooldown scheduler should not run when cooldown is zero")

    monkeypatch.setattr(run, "_run_runnable_items_upfront", fake_run_upfront)
    monkeypatch.setattr(run, "_run_runnable_items_with_harness_cooldown", fail_cooldown_scheduler)

    exit_code = run._run_batch(SimpleNamespace(timeout=None), preview)

    assert exit_code == 0
    assert calls == ["upfront"]
