from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import trace_viewer


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_codex_rollout_events_are_normalized(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.jsonl"
    _write_jsonl(
        rollout,
        [
            {
                "type": "session_meta",
                "timestamp": "2026-04-30T00:00:00.000Z",
                "payload": {
                    "id": "session",
                    "model_provider": "openai",
                    "cwd": "/app/workspace",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-04-30T00:00:01.000Z",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "I will write solution.json."}],
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-04-30T00:00:02.000Z",
                "payload": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "exec_command",
                    "arguments": "{\"cmd\":\"python verifier case solution.json\"}",
                },
            },
            {
                "type": "response_item",
                "timestamp": "2026-04-30T00:00:03.000Z",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "VALID",
                },
            },
        ],
    )

    events = trace_viewer._extract_codex_events(
        rollout,
        preview_chars=80,
        expanded_chars=500,
    )

    assert [event["event_type"] for event in events] == [
        "status",
        "message",
        "tool_call",
        "tool_result",
    ]
    assert events[1]["role"] == "assistant"
    assert "solution_json" in events[1]["tags"]
    assert events[2]["metadata"]["tool_name"] == "exec_command"
    assert "verifier" in events[2]["tags"]
    assert events[3]["title"] == "exec_command"


def test_kimi_context_events_and_latest_context_are_normalized(tmp_path: Path) -> None:
    session = tmp_path / "session_logs" / "sessions" / "workspace" / "session"
    session.mkdir(parents=True)
    _write_jsonl(session / "context.jsonl", [{"role": "user", "content": "old"}])
    latest = session / "context_1.jsonl"
    _write_jsonl(
        latest,
        [
            {"role": "_system_prompt", "content": "system"},
            {"role": "user", "content": "solve"},
            {
                "role": "assistant",
                "content": [{"type": "think", "think": "hidden"}],
                "tool_calls": [
                    {
                        "id": "tool_1",
                        "type": "function",
                        "function": {
                            "name": "Shell",
                            "arguments": "python verifier case solution.json",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tool_1",
                "content": [{"type": "text", "text": "VALID"}],
            },
            {"role": "_usage", "token_count": {"input": 1, "output": 2}},
        ],
    )

    assert trace_viewer._latest_kimi_context(tmp_path / "session_logs") == latest
    events = trace_viewer._extract_kimi_events(
        latest,
        preview_chars=80,
        expanded_chars=500,
    )

    assert [event["event_type"] for event in events] == [
        "message",
        "message",
        "message",
        "tool_call",
        "tool_result",
        "usage",
    ]
    assert events[3]["title"] == "Shell"
    assert "solution_json" in events[3]["tags"]
    assert events[4]["title"] == "Shell"
    assert events[5]["collapsed"] is True


def test_opencode_database_events_are_normalized(tmp_path: Path) -> None:
    db_path = tmp_path / "opencode.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            create table session (
                id text primary key,
                slug text,
                title text,
                version text,
                directory text,
                time_created integer,
                time_updated integer
            );
            create table message (
                id text primary key,
                session_id text,
                data text
            );
            create table part (
                id text primary key,
                message_id text,
                session_id text,
                time_created integer,
                data text
            );
            create table todo (
                session_id text,
                content text,
                status text,
                priority text,
                position integer
            );
            """
        )
        conn.execute(
            "insert into session values (?, ?, ?, ?, ?, ?, ?)",
            ("ses_1", "slug", "Title", "1.0.0", "/app/workspace", 1000, 2000),
        )
        conn.execute(
            "insert into message values (?, ?, ?)",
            ("msg_user", "ses_1", json.dumps({"role": "user"})),
        )
        conn.execute(
            "insert into message values (?, ?, ?)",
            ("msg_assistant", "ses_1", json.dumps({"role": "assistant"})),
        )
        conn.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (
                "part_text",
                "msg_user",
                "ses_1",
                1100,
                json.dumps({"type": "text", "text": "Please solve"}),
            ),
        )
        conn.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (
                "part_reasoning",
                "msg_assistant",
                "ses_1",
                1200,
                json.dumps({"type": "reasoning", "text": "I should inspect files"}),
            ),
        )
        conn.execute(
            "insert into part values (?, ?, ?, ?, ?)",
            (
                "part_tool",
                "msg_assistant",
                "ses_1",
                1300,
                json.dumps(
                    {
                        "type": "tool",
                        "tool": "bash",
                        "callID": "call_1",
                        "state": {
                            "status": "completed",
                            "input": {"command": "python verifier case solution.json"},
                            "output": "VALID",
                        },
                    }
                ),
            ),
        )
        conn.execute(
            "insert into todo values (?, ?, ?, ?, ?)",
            ("ses_1", "Verify solution", "completed", "high", 0),
        )

    events, todos = trace_viewer._extract_opencode_events(
        db_path,
        preview_chars=80,
        expanded_chars=500,
    )

    assert [event["event_type"] for event in events] == [
        "status",
        "message",
        "reasoning",
        "tool",
    ]
    assert events[2]["collapsed"] is True
    assert events[3]["metadata"]["tool_name"] == "bash"
    assert "verifier" in events[3]["tags"]
    assert todos == [
        {
            "content": "Verify solution",
            "status": "completed",
            "priority": "high",
            "position": 0,
        }
    ]


def test_claude_code_session_events_are_normalized(tmp_path: Path) -> None:
    session_log = tmp_path / "claude.jsonl"
    _write_jsonl(
        session_log,
        [
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "timestamp": "2026-05-03T07:00:10.212Z",
                "sessionId": "session_1",
                "content": "Please solve and write solution.json.",
            },
            {
                "type": "attachment",
                "timestamp": "2026-05-03T07:00:10.230Z",
                "sessionId": "session_1",
                "attachment": {
                    "type": "skill_listing",
                    "content": "- brahe",
                    "skillCount": 1,
                    "isInitial": True,
                },
            },
            {
                "type": "user",
                "timestamp": "2026-05-03T07:00:11.000Z",
                "uuid": "user_1",
                "sessionId": "session_1",
                "message": {
                    "role": "user",
                    "content": "Use the files in case/.",
                },
            },
            {
                "type": "assistant",
                "timestamp": "2026-05-03T07:00:12.000Z",
                "uuid": "assistant_1",
                "sessionId": "session_1",
                "message": {
                    "id": "message_1",
                    "role": "assistant",
                    "model": "claude-test",
                    "content": [
                        {"type": "thinking", "thinking": "Need inspect case."},
                        {"type": "text", "text": "I will inspect the case."},
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "Bash",
                            "input": {
                                "command": "python verifier case solution.json",
                                "description": "Verify",
                            },
                        },
                    ],
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 1, "output_tokens": 2},
                },
            },
            {
                "type": "user",
                "timestamp": "2026-05-03T07:00:13.000Z",
                "uuid": "tool_result_1",
                "sessionId": "session_1",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "VALID",
                            "is_error": False,
                        }
                    ],
                },
                "sourceToolAssistantUUID": "assistant_1",
            },
            {
                "type": "last-prompt",
                "lastPrompt": "Please solve...",
                "leafUuid": "leaf_1",
                "sessionId": "session_1",
            },
        ],
    )

    events = trace_viewer._extract_claude_code_events(
        session_log,
        preview_chars=80,
        expanded_chars=500,
    )

    assert [event["event_type"] for event in events] == [
        "status",
        "status",
        "message",
        "reasoning",
        "message",
        "tool_call",
        "tool_result",
        "status",
    ]
    assert events[0]["title"] == "Queue Enqueue"
    assert events[1]["metadata"]["attachment_type"] == "skill_listing"
    assert events[2]["role"] == "user"
    assert events[3]["collapsed"] is True
    assert events[4]["role"] == "assistant"
    assert events[5]["metadata"]["tool_name"] == "Bash"
    assert events[5]["metadata"]["usage"] == {"input_tokens": 1, "output_tokens": 2}
    assert "verifier" in events[5]["tags"]
    assert events[6]["title"] == "Bash"
    assert "verifier" in events[6]["tags"]
    assert "solution_json" in events[0]["tags"]


def test_claude_code_tool_result_errors_are_tagged(tmp_path: Path) -> None:
    session_log = tmp_path / "claude.jsonl"
    _write_jsonl(
        session_log,
        [
            {
                "type": "assistant",
                "timestamp": "2026-05-03T07:00:12.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "Read",
                            "input": {"file_path": "missing.json"},
                        }
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2026-05-03T07:00:13.000Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_1",
                            "content": "",
                            "is_error": True,
                        }
                    ],
                },
                "toolUseResult": "Error: file not found",
            },
        ],
    )

    events = trace_viewer._extract_claude_code_events(
        session_log,
        preview_chars=80,
        expanded_chars=500,
    )

    assert [event["event_type"] for event in events] == ["tool_call", "tool_result"]
    assert events[1]["title"] == "Read"
    assert events[1]["text"] == "Error: file not found"
    assert "error" in events[1]["tags"]
    assert events[1]["metadata"]["is_error"] is True


def test_trace_data_files_are_browser_loadable(tmp_path: Path) -> None:
    output_dir = tmp_path / "traces"
    runs = [{"id": "run_1", "data_file": "data/events/run_1.js"}]
    events = {"run_1": [{"id": "event_1", "text": "hello"}]}

    trace_viewer._write_trace_data(output_dir, runs, events)

    assert "window.TRACE_RUNS" in (output_dir / "data" / "runs.js").read_text(
        encoding="utf-8"
    )
    event_text = (output_dir / "data" / "events" / "run_1.js").read_text(encoding="utf-8")
    assert "window.TRACE_EVENTS" in event_text
    assert "event_1" in event_text


def test_trace_source_detection_uses_harness_log_conventions(tmp_path: Path) -> None:
    output_dir = tmp_path / "run"
    logs = output_dir / "session_logs"

    codex_rollout = logs / "sessions" / "2026" / "05" / "10" / "rollout-2.jsonl"
    codex_rollout.parent.mkdir(parents=True)
    codex_rollout.write_text("{}\n", encoding="utf-8")

    kimi_context = logs / "sessions" / "workspace" / "session" / "context_3.jsonl"
    kimi_context.parent.mkdir(parents=True, exist_ok=True)
    kimi_context.write_text("{}\n", encoding="utf-8")

    opencode_db = logs / "opencode" / "opencode.db"
    opencode_db.parent.mkdir(parents=True, exist_ok=True)
    opencode_db.write_text("", encoding="utf-8")

    claude_log = logs / "projects" / "-app-workspace" / "session.jsonl"
    claude_log.parent.mkdir(parents=True, exist_ok=True)
    claude_log.write_text("{}\n", encoding="utf-8")

    namespaced_claude_log = (
        logs / "claude_code_dpsk" / "projects" / "-app-workspace" / "session.jsonl"
    )
    namespaced_claude_log.parent.mkdir(parents=True, exist_ok=True)
    namespaced_claude_log.write_text("{}\n", encoding="utf-8")

    codex_source = trace_viewer._find_trace_source(output_dir, "codex")
    kimi_source = trace_viewer._find_trace_source(output_dir, "kimi_cli")
    opencode_source = trace_viewer._find_trace_source(output_dir, "opencode_dpsk")
    claude_source = trace_viewer._find_trace_source(output_dir, "claude_code")

    assert codex_source is not None
    assert codex_source.kind == "codex"
    assert codex_source.path == codex_rollout
    assert kimi_source is not None
    assert kimi_source.kind == "kimi_cli"
    assert kimi_source.path == kimi_context
    assert opencode_source is not None
    assert opencode_source.kind == "opencode"
    assert opencode_source.path == opencode_db
    assert claude_source is not None
    assert claude_source.kind == "claude_code"
    assert claude_source.path == claude_log
    assert trace_viewer._find_trace_source(output_dir, "unknown_harness") is None

    claude_log.unlink()
    namespaced_source = trace_viewer._find_trace_source(output_dir, "claude_code_dpsk")
    assert namespaced_source is not None
    assert namespaced_source.kind == "claude_code"
    assert namespaced_source.path == namespaced_claude_log
