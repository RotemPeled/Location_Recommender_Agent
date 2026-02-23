from __future__ import annotations

import contextvars
import uuid

_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def start_new_turn() -> str:
    """Create and set a new correlation id for one user turn."""
    correlation_id = str(uuid.uuid4())[:8]
    _CORRELATION_ID.set(correlation_id)
    return correlation_id


def set_correlation_id(value: str) -> None:
    _CORRELATION_ID.set(value)


def get_correlation_id() -> str:
    return _CORRELATION_ID.get()
