"""Small wall-clock timing helpers for solver debug summaries."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator


class PhaseTimer:
    def __init__(self) -> None:
        self._elapsed_by_name: dict[str, float] = {}

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self._elapsed_by_name[name] = (
                self._elapsed_by_name.get(name, 0.0) + perf_counter() - started
            )

    def as_dict(self) -> dict[str, float]:
        return dict(sorted(self._elapsed_by_name.items()))
