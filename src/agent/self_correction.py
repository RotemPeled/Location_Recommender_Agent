from __future__ import annotations

from typing import Any

from src.core.logger import log_event


def validate_candidates(
    candidates: list[dict[str, Any]],
    max_flight_hours: float | None,
    rejected_destinations: set[str],
    logger: Any,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        name = candidate.get("destination", "").lower()
        if name in rejected_destinations:
            log_event(logger, "INFO", "candidate_excluded_rejected", destination=name)
            continue
        if max_flight_hours is not None:
            est = candidate.get("estimated_flight_hours")
            if isinstance(est, (float, int)) and est > max_flight_hours:
                log_event(
                    logger,
                    "INFO",
                    "candidate_excluded_flight_limit",
                    destination=name,
                    estimated_flight_hours=est,
                    max_flight_hours=max_flight_hours,
                )
                continue
        filtered.append(candidate)
    return filtered


def maybe_retry_tools(
    data: Any,
    logger: Any,
) -> Any:
    # Placeholder hook for future retries and fallback policies.
    log_event(logger, "DEBUG", "self_correction_retry_hook", active=True)
    return data
