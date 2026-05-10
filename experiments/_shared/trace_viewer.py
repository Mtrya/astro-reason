#!/usr/bin/env python3
"""Shared trace-viewer parsing and static rendering helpers."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FAMILY_DIR = Path(__file__).resolve().parent
PREVIEW_CHARS = 280
EXPANDED_CHARS = 6000
TRACE_EVENTS_GLOBAL = "window.TRACE_EVENTS"
TRACE_RUNS_GLOBAL = "window.TRACE_RUNS"
SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class TraceSource:
    kind: str
    path: Path


def _relative_display(path: Path, repo_root: Path | None = None) -> str:
    if repo_root is not None and path.is_relative_to(repo_root):
        return path.relative_to(repo_root).as_posix()
    return str(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except OSError:
        return []
    return rows


def _safe_run_id(parts: tuple[str, ...]) -> str:
    return SAFE_ID_PATTERN.sub("_", "__".join(parts)).strip("_")


def _js_assign(name: str, value: Any) -> str:
    return f"{name} = {json.dumps(value, ensure_ascii=False, separators=(',', ':'))};\n"


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_flatten_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "output", "message", "summary"):
            if key in value:
                text = _flatten_text(value[key])
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _content_text(content: Any) -> str:
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(_flatten_text(item))
            else:
                parts.append(_flatten_text(item))
        return "\n".join(part for part in parts if part)
    return _flatten_text(content)


def _truncate_text(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    head_len = max(0, limit // 2)
    tail_len = max(0, limit - head_len)
    omitted = len(text) - head_len - tail_len
    return (
        text[:head_len]
        + f"\n\n[... truncated {omitted} characters ...]\n\n"
        + text[-tail_len:],
        True,
    )


def _preview(text: str, limit: int) -> str:
    preview, truncated = _truncate_text(" ".join(text.split()), limit)
    if truncated:
        return preview + " ..."
    return preview


def _timestamp_ms(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError:
        return None


def _event(
    *,
    source: str,
    event_type: str,
    role: str,
    title: str,
    text: str,
    seq: int,
    timestamp: str | None = None,
    timestamp_ms: int | None = None,
    collapsed: bool = False,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    preview_chars: int = PREVIEW_CHARS,
    expanded_chars: int = EXPANDED_CHARS,
) -> dict[str, Any]:
    expanded, truncated = _truncate_text(text or "", expanded_chars)
    event_tags = set(tags or [])
    haystack = " ".join([title, text or ""]).lower()
    if "solution.json" in haystack:
        event_tags.add("solution_json")
    if "verifier" in haystack or "valid" in haystack or "invalid" in haystack:
        event_tags.add("verifier")
    if "error" in haystack or "failed" in haystack or "traceback" in haystack:
        event_tags.add("error")
    if "timeout" in haystack:
        event_tags.add("timeout")
    return {
        "id": f"{source}-{seq}",
        "seq": seq,
        "timestamp": timestamp,
        "timestamp_ms": timestamp_ms,
        "source": source,
        "event_type": event_type,
        "role": role,
        "title": title,
        "preview": _preview(text or title, preview_chars),
        "text": expanded,
        "truncated": truncated,
        "collapsed": collapsed,
        "tags": sorted(event_tags),
        "metadata": metadata or {},
    }


def _extract_codex_events(
    path: Path,
    *,
    preview_chars: int,
    expanded_chars: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    call_names: dict[str, str] = {}
    for row in _read_jsonl(path):
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        timestamp = row.get("timestamp") if isinstance(row.get("timestamp"), str) else None
        timestamp_ms = _timestamp_ms(timestamp)
        seq = len(events)
        row_type = row.get("type")
        payload_type = payload.get("type")
        if row_type == "session_meta":
            events.append(
                _event(
                    source="codex",
                    event_type="status",
                    role="system",
                    title="Session",
                    text=f"model={payload.get('model_provider')} cwd={payload.get('cwd')}",
                    seq=seq,
                    timestamp=timestamp,
                    timestamp_ms=timestamp_ms,
                    collapsed=True,
                    metadata={key: payload.get(key) for key in ("id", "source", "cli_version")},
                    preview_chars=preview_chars,
                    expanded_chars=expanded_chars,
                )
            )
        elif row_type == "event_msg":
            event_type = str(payload_type or "event")
            text = _flatten_text(payload.get("message") or payload.get("text_elements") or payload)
            role = "assistant" if event_type == "agent_message" else "system"
            events.append(
                _event(
                    source="codex",
                    event_type="message" if event_type in {"agent_message", "user_message"} else "status",
                    role=role,
                    title=event_type.replace("_", " ").title(),
                    text=text,
                    seq=seq,
                    timestamp=timestamp,
                    timestamp_ms=timestamp_ms,
                    collapsed=event_type == "token_count",
                    metadata={"codex_event_type": event_type},
                    preview_chars=preview_chars,
                    expanded_chars=expanded_chars,
                )
            )
        elif row_type == "response_item":
            if payload_type == "message":
                role = str(payload.get("role") or "assistant")
                if role == "developer":
                    role = "system"
                text = _content_text(payload.get("content"))
                events.append(
                    _event(
                        source="codex",
                        event_type="message",
                        role=role,
                        title=role.title(),
                        text=text,
                        seq=seq,
                        timestamp=timestamp,
                        timestamp_ms=timestamp_ms,
                        metadata={"payload_type": payload_type},
                        preview_chars=preview_chars,
                        expanded_chars=expanded_chars,
                    )
                )
            elif payload_type == "reasoning":
                text = _content_text(payload.get("summary") or payload.get("content") or "")
                events.append(
                    _event(
                        source="codex",
                        event_type="reasoning",
                        role="reasoning",
                        title="Reasoning",
                        text=text or "[reasoning block]",
                        seq=seq,
                        timestamp=timestamp,
                        timestamp_ms=timestamp_ms,
                        collapsed=True,
                        metadata={"payload_type": payload_type},
                        preview_chars=preview_chars,
                        expanded_chars=expanded_chars,
                    )
                )
            elif payload_type in {"function_call", "custom_tool_call"}:
                call_id = str(payload.get("call_id") or payload.get("id") or "")
                name = str(payload.get("name") or payload_type)
                if call_id:
                    call_names[call_id] = name
                text = _flatten_text(payload.get("arguments") or payload.get("input") or "")
                events.append(
                    _event(
                        source="codex",
                        event_type="tool_call",
                        role="assistant",
                        title=name,
                        text=text,
                        seq=seq,
                        timestamp=timestamp,
                        timestamp_ms=timestamp_ms,
                        collapsed=True,
                        metadata={"call_id": call_id, "tool_name": name, "payload_type": payload_type},
                        preview_chars=preview_chars,
                        expanded_chars=expanded_chars,
                    )
                )
            elif payload_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(payload.get("call_id") or payload.get("id") or "")
                name = call_names.get(call_id, "tool result")
                text = _flatten_text(payload.get("output") or payload.get("content") or "")
                events.append(
                    _event(
                        source="codex",
                        event_type="tool_result",
                        role="tool",
                        title=name,
                        text=text,
                        seq=seq,
                        timestamp=timestamp,
                        timestamp_ms=timestamp_ms,
                        collapsed=True,
                        metadata={"call_id": call_id, "tool_name": name, "payload_type": payload_type},
                        preview_chars=preview_chars,
                        expanded_chars=expanded_chars,
                    )
                )
    return events


def _latest_kimi_context(session_logs: Path) -> Path | None:
    candidates = sorted(session_logs.glob("sessions/*/*/context*.jsonl"))
    if not candidates:
        return None

    def key(path: Path) -> tuple[int, str]:
        match = re.search(r"context(?:_(\d+))?\.jsonl$", path.name)
        return (int(match.group(1) or 0) if match else 0, path.as_posix())

    return max(candidates, key=key)


def _extract_kimi_events(
    path: Path,
    *,
    preview_chars: int,
    expanded_chars: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    call_names: dict[str, str] = {}
    for row in _read_jsonl(path):
        role = row.get("role")
        if not isinstance(role, str):
            continue
        seq = len(events)
        if role == "_checkpoint":
            events.append(
                _event(
                    source="kimi_cli",
                    event_type="checkpoint",
                    role="status",
                    title="Checkpoint",
                    text=str(row.get("id") or "checkpoint"),
                    seq=seq,
                    collapsed=True,
                    metadata={"id": row.get("id")},
                    preview_chars=preview_chars,
                    expanded_chars=expanded_chars,
                )
            )
            continue
        if role == "_usage":
            events.append(
                _event(
                    source="kimi_cli",
                    event_type="usage",
                    role="status",
                    title="Usage",
                    text=json.dumps(row.get("token_count"), ensure_ascii=False, sort_keys=True),
                    seq=seq,
                    collapsed=True,
                    metadata={"token_count": row.get("token_count")},
                    preview_chars=preview_chars,
                    expanded_chars=expanded_chars,
                )
            )
            continue

        viewer_role = "system" if role == "_system_prompt" else role
        event_type = "message" if viewer_role in {"system", "user", "assistant"} else "tool_result"
        text = _content_text(row.get("content"))
        title = viewer_role.title()
        events.append(
            _event(
                source="kimi_cli",
                event_type=event_type,
                role=viewer_role if viewer_role in {"system", "user", "assistant", "tool"} else "status",
                title=title,
                text=text,
                seq=seq,
                collapsed=viewer_role == "system" or viewer_role == "tool",
                metadata={"tool_call_id": row.get("tool_call_id")} if row.get("tool_call_id") else {},
                preview_chars=preview_chars,
                expanded_chars=expanded_chars,
            )
        )

        tool_calls = row.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                function = function if isinstance(function, dict) else {}
                call_id = str(call.get("id") or "")
                name = str(function.get("name") or call.get("type") or "tool")
                if call_id:
                    call_names[call_id] = name
                events.append(
                    _event(
                        source="kimi_cli",
                        event_type="tool_call",
                        role="assistant",
                        title=name,
                        text=_flatten_text(function.get("arguments")),
                        seq=len(events),
                        collapsed=True,
                        metadata={"call_id": call_id, "tool_name": name, "call_type": call.get("type")},
                        preview_chars=preview_chars,
                        expanded_chars=expanded_chars,
                    )
                )
    for event in events:
        call_id = event["metadata"].get("tool_call_id")
        if call_id and call_id in call_names:
            event["title"] = call_names[call_id]
            event["metadata"]["tool_name"] = call_names[call_id]
    return events


def _json_from_sql(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_opencode_events(
    path: Path,
    *,
    preview_chars: int,
    expanded_chars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    todos: list[dict[str, Any]] = []
    uri = f"file:{path}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                "select id, slug, title, version, directory, time_created, time_updated from session order by time_created"
            ):
                events.append(
                    _event(
                        source="opencode",
                        event_type="status",
                        role="system",
                        title="Session",
                        text=f"{row['title']} ({row['slug']})",
                        seq=len(events),
                        timestamp_ms=int(row["time_created"]),
                        collapsed=True,
                        metadata={
                            "session_id": row["id"],
                            "version": row["version"],
                            "directory": row["directory"],
                        },
                        preview_chars=preview_chars,
                        expanded_chars=expanded_chars,
                    )
                )
            message_roles = {
                row["id"]: _json_from_sql(row["data"]).get("role", "assistant")
                for row in conn.execute("select id, data from message")
            }
            for row in conn.execute(
                "select id, message_id, session_id, time_created, data from part order by time_created, id"
            ):
                data = _json_from_sql(row["data"])
                part_type = str(data.get("type") or "part")
                role = str(message_roles.get(row["message_id"]) or "assistant")
                metadata = {
                    "part_id": row["id"],
                    "message_id": row["message_id"],
                    "session_id": row["session_id"],
                    "part_type": part_type,
                }
                if part_type == "tool":
                    state = data.get("state") if isinstance(data.get("state"), dict) else {}
                    tool = str(data.get("tool") or "tool")
                    metadata.update(
                        {
                            "call_id": data.get("callID"),
                            "tool_name": tool,
                            "status": state.get("status"),
                            "input": state.get("input"),
                            "metadata": state.get("metadata"),
                        }
                    )
                    events.append(
                        _event(
                            source="opencode",
                            event_type="tool",
                            role="tool",
                            title=f"{tool}: {state.get('status') or 'unknown'}",
                            text=_flatten_text(state.get("output") or state.get("metadata") or state),
                            seq=len(events),
                            timestamp_ms=int(row["time_created"]),
                            collapsed=True,
                            tags=["error"] if state.get("status") == "error" else [],
                            metadata=metadata,
                            preview_chars=preview_chars,
                            expanded_chars=expanded_chars,
                        )
                    )
                elif part_type == "reasoning":
                    events.append(
                        _event(
                            source="opencode",
                            event_type="reasoning",
                            role="reasoning",
                            title="Reasoning",
                            text=_flatten_text(data.get("text") or ""),
                            seq=len(events),
                            timestamp_ms=int(row["time_created"]),
                            collapsed=True,
                            metadata=metadata,
                            preview_chars=preview_chars,
                            expanded_chars=expanded_chars,
                        )
                    )
                elif part_type == "text":
                    events.append(
                        _event(
                            source="opencode",
                            event_type="message",
                            role="user" if role == "user" else "assistant",
                            title=role.title(),
                            text=_flatten_text(data.get("text") or ""),
                            seq=len(events),
                            timestamp_ms=int(row["time_created"]),
                            metadata=metadata,
                            preview_chars=preview_chars,
                            expanded_chars=expanded_chars,
                        )
                    )
                elif part_type == "step-finish":
                    events.append(
                        _event(
                            source="opencode",
                            event_type="usage",
                            role="status",
                            title="Step Finish",
                            text=json.dumps(data.get("tokens"), ensure_ascii=False, sort_keys=True),
                            seq=len(events),
                            timestamp_ms=int(row["time_created"]),
                            collapsed=True,
                            metadata={**metadata, "reason": data.get("reason"), "tokens": data.get("tokens")},
                            preview_chars=preview_chars,
                            expanded_chars=expanded_chars,
                        )
                    )
                elif part_type == "step-start":
                    events.append(
                        _event(
                            source="opencode",
                            event_type="status",
                            role="status",
                            title="Step Start",
                            text="step-start",
                            seq=len(events),
                            timestamp_ms=int(row["time_created"]),
                            collapsed=True,
                            metadata=metadata,
                            preview_chars=preview_chars,
                            expanded_chars=expanded_chars,
                        )
                    )
            for row in conn.execute(
                "select content, status, priority, position from todo order by position"
            ):
                todos.append(
                    {
                        "content": row["content"],
                        "status": row["status"],
                        "priority": row["priority"],
                        "position": row["position"],
                    }
                )
    except sqlite3.Error:
        return events, todos
    return events, todos


def _find_trace_source(output_dir: Path, harness: str) -> TraceSource | None:
    logs_dir = output_dir / "session_logs"
    if harness == "codex":
        candidates = sorted(logs_dir.glob("sessions/*/*/*/rollout-*.jsonl"))
        if candidates:
            return TraceSource("codex", candidates[-1])
    if harness == "kimi_cli":
        context = _latest_kimi_context(logs_dir)
        if context is not None:
            return TraceSource("kimi_cli", context)
    if harness.startswith("opencode"):
        db_path = logs_dir / "opencode" / "opencode.db"
        if db_path.exists():
            return TraceSource("opencode", db_path)
    return None


def _metric_summary(verifier: dict[str, Any]) -> dict[str, Any]:
    metrics = verifier.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def _event_summary(events: list[dict[str, Any]], todos: list[dict[str, Any]]) -> dict[str, Any]:
    event_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    failed_tools = 0
    first_solution_event: int | None = None
    for event in events:
        event_counts[event["event_type"]] = event_counts.get(event["event_type"], 0) + 1
        tool_name = event["metadata"].get("tool_name")
        if tool_name:
            tool_counts[str(tool_name)] = tool_counts.get(str(tool_name), 0) + 1
        if event["metadata"].get("status") == "error" or "error" in event["tags"]:
            failed_tools += 1
        if first_solution_event is None and "solution_json" in event["tags"]:
            first_solution_event = event["seq"]
    return {
        "event_counts": dict(sorted(event_counts.items())),
        "tool_counts": dict(sorted(tool_counts.items())),
        "failed_tools": failed_tools,
        "first_solution_event": first_solution_event,
        "todos": todos,
    }


def _load_trace_events(
    source: TraceSource,
    *,
    preview_chars: int,
    expanded_chars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if source.kind == "codex":
        return (
            _extract_codex_events(
                source.path,
                preview_chars=preview_chars,
                expanded_chars=expanded_chars,
            ),
            [],
        )
    if source.kind == "kimi_cli":
        return (
            _extract_kimi_events(
                source.path,
                preview_chars=preview_chars,
                expanded_chars=expanded_chars,
            ),
            [],
        )
    if source.kind == "opencode":
        return _extract_opencode_events(
            source.path,
            preview_chars=preview_chars,
            expanded_chars=expanded_chars,
        )
    return [], []


def _write_index_html(output_dir: Path) -> None:
    html = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Main Agentic Trace Viewer</title>
  <style>
    :root { color-scheme: light; --bg:#f6f7f9; --panel:#fff; --line:#d9dee7; --text:#172033; --muted:#647084; --accent:#2563eb; --assistant:#eef4ff; --user:#f3f0ff; --tool:#f6f8fa; --reason:#fff7df; --error:#fff1f0; }
    * { box-sizing:border-box; }
    body { margin:0; font:14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); }
    .app { display:grid; grid-template-columns:320px minmax(0,1fr) 280px; height:100vh; }
    aside, main, .details { min-height:0; }
    aside { border-right:1px solid var(--line); background:var(--panel); display:flex; flex-direction:column; }
    .sidebar-head { padding:14px; border-bottom:1px solid var(--line); }
    h1 { margin:0 0 10px; font-size:18px; }
    input, select { width:100%; border:1px solid var(--line); border-radius:6px; padding:8px; background:#fff; color:var(--text); }
    .filters { display:grid; gap:8px; }
    .run-list { overflow:auto; padding:8px; }
    .run { width:100%; text-align:left; background:#fff; border:1px solid transparent; border-radius:8px; padding:10px; margin:0 0 8px; cursor:pointer; }
    .run:hover, .run.active { border-color:var(--accent); }
    .run-title { font-weight:650; }
    .run-meta { color:var(--muted); font-size:12px; margin-top:3px; }
    main { display:flex; flex-direction:column; min-width:0; }
    .topbar { background:var(--panel); border-bottom:1px solid var(--line); padding:12px 18px; }
    .topline { display:flex; flex-wrap:wrap; gap:8px 14px; align-items:center; }
    .badge { border:1px solid var(--line); border-radius:999px; padding:3px 9px; background:#fff; font-size:12px; }
    .badge.success { color:#166534; background:#eefdf3; border-color:#bbf7d0; }
    .badge.error { color:#991b1b; background:#fff1f0; border-color:#fecaca; }
    .chat { overflow:auto; padding:18px; }
    .bubble { max-width:980px; border:1px solid var(--line); border-radius:8px; background:#fff; margin:0 0 12px; overflow:hidden; }
    .bubble.user { background:var(--user); }
    .bubble.assistant { background:var(--assistant); }
    .bubble.tool, .bubble.status { background:var(--tool); }
    .bubble.reasoning { background:var(--reason); }
    .bubble.error-tag { border-color:#fca5a5; background:var(--error); }
    .bubble-head { display:flex; justify-content:space-between; gap:10px; padding:8px 10px; border-bottom:1px solid rgba(0,0,0,.06); color:var(--muted); font-size:12px; }
    .bubble-title { font-weight:700; color:var(--text); }
    .bubble-body { padding:10px; white-space:pre-wrap; overflow-wrap:anywhere; }
    details { padding:0 10px 10px; }
    summary { cursor:pointer; color:var(--accent); font-size:12px; }
    pre { margin:8px 0 0; padding:10px; border-radius:6px; background:#0f172a; color:#dbeafe; overflow:auto; max-height:420px; }
    .details { border-left:1px solid var(--line); background:var(--panel); overflow:auto; padding:14px; }
    .details h2 { margin:0 0 10px; font-size:16px; }
    .kv { display:grid; grid-template-columns:1fr auto; gap:6px 10px; font-size:13px; margin-bottom:14px; }
    .kv div:nth-child(odd) { color:var(--muted); }
    .empty { color:var(--muted); padding:24px; }
    @media (max-width: 980px) { .app { grid-template-columns:1fr; } aside, .details { height:36vh; border:0; border-bottom:1px solid var(--line); } }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="sidebar-head">
        <h1>Trace Viewer</h1>
        <div class="filters">
          <input id="search" placeholder="Search benchmark, harness, case">
          <select id="harness"><option value="">All harnesses</option></select>
          <select id="status"><option value="">All statuses</option></select>
        </div>
      </div>
      <div id="runList" class="run-list"></div>
    </aside>
    <main>
      <div id="topbar" class="topbar"><div class="empty">Select a run to inspect its trace.</div></div>
      <div id="chat" class="chat"></div>
    </main>
    <section id="details" class="details"><h2>Run Details</h2><div class="empty">No run selected.</div></section>
  </div>
  <script src="data/runs.js"></script>
  <script>
    const loaded = new Set();
    const state = { selected: null };
    const runs = (window.TRACE_RUNS || []).slice().sort((a, b) => `${a.benchmark}/${a.harness}/${a.case_id}`.localeCompare(`${b.benchmark}/${b.harness}/${b.case_id}`));
    const runList = document.getElementById('runList');
    const search = document.getElementById('search');
    const harness = document.getElementById('harness');
    const status = document.getElementById('status');
    const topbar = document.getElementById('topbar');
    const chat = document.getElementById('chat');
    const details = document.getElementById('details');

    function uniq(values) { return [...new Set(values.filter(Boolean))].sort(); }
    function opt(select, value) { const o = document.createElement('option'); o.value = value; o.textContent = value; select.appendChild(o); }
    uniq(runs.map(r => r.harness)).forEach(v => opt(harness, v));
    uniq(runs.map(r => r.overall_status)).forEach(v => opt(status, v));

    function metricText(run) {
      const entries = Object.entries(run.metrics || {}).filter(([, v]) => v !== null && v !== undefined && v !== '');
      return entries.slice(0, 3).map(([k, v]) => `${k}=${typeof v === 'number' ? Number(v.toFixed(4)) : v}`).join(' · ');
    }
    function matches(run) {
      const q = search.value.toLowerCase();
      const hay = `${run.benchmark} ${run.harness} ${run.case_id} ${run.overall_status}`.toLowerCase();
      return (!q || hay.includes(q)) && (!harness.value || run.harness === harness.value) && (!status.value || run.overall_status === status.value);
    }
    function renderRuns() {
      runList.innerHTML = '';
      runs.filter(matches).forEach(run => {
        const button = document.createElement('button');
        button.className = 'run' + (state.selected === run.id ? ' active' : '');
        button.innerHTML = `<div class="run-title">${run.benchmark} / ${run.case_id}</div><div class="run-meta">${run.harness} · ${run.overall_status} · ${run.event_count || 0} events</div>`;
        button.onclick = () => selectRun(run);
        runList.appendChild(button);
      });
    }
    function loadScript(src) {
      return new Promise((resolve, reject) => {
        if (loaded.has(src)) return resolve();
        const s = document.createElement('script');
        s.src = src;
        s.onload = () => { loaded.add(src); resolve(); };
        s.onerror = reject;
        document.body.appendChild(s);
      });
    }
    async function selectRun(run) {
      state.selected = run.id;
      renderRuns();
      topbar.innerHTML = `<div class="topline"><strong>${run.benchmark} / ${run.harness} / ${run.case_id}</strong><span class="badge ${run.overall_status === 'success' ? 'success' : 'error'}">${run.overall_status}</span><span class="badge">valid: ${run.valid ?? '-'}</span><span class="badge">${run.duration_seconds ?? '-'}s</span><span>${metricText(run)}</span></div>`;
      chat.innerHTML = '<div class="empty">Loading trace...</div>';
      await loadScript(run.data_file);
      const events = (window.TRACE_EVENTS && window.TRACE_EVENTS[run.id]) || [];
      renderChat(events);
      renderDetails(run, events);
    }
    function renderChat(events) {
      chat.innerHTML = '';
      if (!events.length) { chat.innerHTML = '<div class="empty">No trace events found for this run.</div>'; return; }
      events.forEach(event => {
        const bubble = document.createElement('article');
        bubble.className = `bubble ${event.role || 'status'} ${event.tags && event.tags.includes('error') ? 'error-tag' : ''}`;
        const meta = [event.event_type, (event.tags || []).join(', ')].filter(Boolean).join(' · ');
        const body = document.createElement('div');
        body.className = 'bubble-body';
        body.textContent = event.preview || event.title;
        bubble.innerHTML = `<div class="bubble-head"><span class="bubble-title">${event.title || event.role}</span><span>${meta}</span></div>`;
        bubble.appendChild(body);
        if (event.collapsed || event.truncated || (event.text && event.text !== event.preview)) {
          const details = document.createElement('details');
          if (!event.collapsed && event.truncated) details.open = true;
          details.innerHTML = '<summary>details</summary>';
          const pre = document.createElement('pre');
          pre.textContent = event.text || '';
          details.appendChild(pre);
          bubble.appendChild(details);
        }
        chat.appendChild(bubble);
      });
    }
    function renderDetails(run, events) {
      const counts = {};
      const tools = {};
      events.forEach(e => {
        counts[e.event_type] = (counts[e.event_type] || 0) + 1;
        const tool = e.metadata && e.metadata.tool_name;
        if (tool) tools[tool] = (tools[tool] || 0) + 1;
      });
      const kv = (obj) => Object.entries(obj).map(([k,v]) => `<div>${k}</div><div>${v}</div>`).join('');
      details.innerHTML = `<h2>Run Details</h2><div class="kv">${kv({Benchmark: run.benchmark, Harness: run.harness, Case: run.case_id, Status: run.overall_status, Valid: run.valid ?? '-', Duration: run.duration_seconds ?? '-', Events: events.length, Source: run.trace_source || '-'})}</div><h2>Event Counts</h2><div class="kv">${kv(counts)}</div><h2>Tool Counts</h2><div class="kv">${kv(tools)}</div>`;
    }
    [search, harness, status].forEach(el => el.addEventListener('input', renderRuns));
    renderRuns();
    if (runs.length) selectRun(runs[0]);
  </script>
</body>
</html>
"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def _write_trace_data(
    output_dir: Path,
    runs: list[dict[str, Any]],
    events_by_run: dict[str, list[dict[str, Any]]],
) -> None:
    data_dir = output_dir / "data"
    events_dir = data_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "runs.js").write_text(_js_assign(TRACE_RUNS_GLOBAL, runs), encoding="utf-8")
    for run in runs:
        run_id = run["id"]
        content = (
            f"{TRACE_EVENTS_GLOBAL} = {TRACE_EVENTS_GLOBAL} || {{}};\n"
            f"{TRACE_EVENTS_GLOBAL}[{json.dumps(run_id)}] = "
            f"{json.dumps(events_by_run.get(run_id, []), ensure_ascii=False, separators=(',', ':'))};\n"
        )
        (events_dir / f"{run_id}.js").write_text(content, encoding="utf-8")

