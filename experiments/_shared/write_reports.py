"""Shared helpers for experiment report writers."""

from __future__ import annotations


def format_value(value: str | None) -> str:
    if value in (None, ""):
        return "-"
    if value in {"True", "False"}:
        return value.lower()
    try:
        numeric = float(value)
    except ValueError:
        return value
    if numeric.is_integer() and "." not in value.lower().split("e", maxsplit=1)[0]:
        return str(int(numeric))
    if abs(numeric) >= 100:
        return f"{numeric:.1f}"
    if abs(numeric) >= 10:
        return f"{numeric:.2f}"
    return f"{numeric:.4f}"


def metric_columns(
    rows: list[dict[str, str]],
    *,
    standard_columns: set[str],
    processed_metric_columns: set[str],
) -> list[str]:
    if not rows:
        return []
    fieldnames = list(rows[0])
    return [
        name
        for name in fieldnames
        if name not in standard_columns
        and name not in processed_metric_columns
        and any(row.get(name) not in (None, "") for row in rows)
    ]


def valid_value(row: dict[str, str]) -> bool:
    return row.get("valid") == "True"


def table(headers: list[str], rows: list[list[str]], *, numeric_from: int = 0) -> list[str]:
    align = ["---"] * len(headers)
    for index in range(numeric_from, len(headers)):
        align[index] = "---:"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(align) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def summary_rows(
    benchmark: str,
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("benchmark") == benchmark and row.get("present_runs") not in ("", "0")
    ]
