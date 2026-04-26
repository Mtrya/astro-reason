"""Backend selection for the AEOSSP MWIS solver."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MWIS_BACKENDS = ("internal_reduction", "fallback_python", "redumis")


@dataclass(frozen=True, slots=True)
class BackendResolution:
    requested_backend: str
    backend: str
    backend_available: bool
    backend_fallback_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_backend(requested_backend: str) -> BackendResolution:
    if requested_backend == "redumis":
        return BackendResolution(
            requested_backend=requested_backend,
            backend="fallback_python",
            backend_available=False,
            backend_fallback_reason=(
                "redumis backend is not bundled with this solver; using the "
                "deterministic Python reduction-backed fallback"
            ),
        )
    return BackendResolution(
        requested_backend=requested_backend,
        backend=requested_backend,
        backend_available=True,
    )


def parse_backend(value: Any) -> str:
    backend = "internal_reduction" if value in {None, ""} else str(value)
    if backend not in MWIS_BACKENDS:
        raise ValueError(
            "backend must be one of: internal_reduction, fallback_python, redumis"
        )
    return backend
