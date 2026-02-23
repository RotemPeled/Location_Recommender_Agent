from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.core.logging_context import get_correlation_id

LEVELS = {"TRACE": 5, "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARN": logging.WARNING, "ERROR": logging.ERROR}

logging.addLevelName(5, "TRACE")


def _trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(5):
        self._log(5, message, args, **kwargs)


logging.Logger.trace = _trace  # type: ignore[attr-defined]


def _safe_payload(payload: dict[str, Any], level_name: str) -> dict[str, Any]:
    redacted = {}
    for key, value in payload.items():
        lower = key.lower()
        if any(secret in lower for secret in ("key", "token", "authorization")):
            redacted[key] = "***REDACTED***"
            continue
        if level_name != "TRACE" and isinstance(value, (dict, list)):
            raw = json.dumps(value, default=str)
            redacted[key] = raw[:600] + ("..." if len(raw) > 600 else "")
            continue
        redacted[key] = value
    return redacted


def setup_logger() -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = LEVELS.get(level_name, logging.INFO)

    logger = logging.getLogger("travel_agent")
    logger.handlers.clear()
    logger.setLevel(level)

    handler = logging.StreamHandler()
    pretty = os.getenv("LOG_PRETTY", "true").lower() == "true"
    if pretty:
        fmt = "%(asctime)s | %(levelname)s | corr=%(correlation_id)s | %(message)s"
    else:
        fmt = "%(levelname)s corr=%(correlation_id)s %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    level_name: str,
    event: str,
    **payload: Any,
) -> None:
    level_name = level_name.upper()
    corr = get_correlation_id() or "-"
    safe_payload = _safe_payload(payload, level_name)
    message = f"{event} | {json.dumps(safe_payload, default=str)}"
    extra = {"correlation_id": corr}
    if level_name == "TRACE":
        logger.trace(message, extra=extra)  # type: ignore[attr-defined]
    elif level_name == "DEBUG":
        logger.debug(message, extra=extra)
    elif level_name == "INFO":
        logger.info(message, extra=extra)
    elif level_name in ("WARN", "WARNING"):
        logger.warning(message, extra=extra)
    else:
        logger.error(message, extra=extra)
