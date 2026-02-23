from __future__ import annotations

import time
from typing import Any

import requests

from src.core.logger import log_event


class PlacesTool:
    def __init__(self, logger: Any) -> None:
        self.logger = logger
        self.urls = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter",
        ]
        self.overpass_backoff_until = 0.0

    def fetch_activity_signals(self, lat: float, lon: float, activity: str | None) -> dict[str, Any]:
        start = time.time()
        if time.time() < self.overpass_backoff_until:
            fallback = self._fallback_result(activity)
            log_event(
                self.logger,
                "WARN",
                "places_backoff_active",
                backoff_until=self.overpass_backoff_until,
                fallback=fallback,
            )
            return fallback
        tag = self._activity_tag(activity)
        query = (
            "[out:json][timeout:25];"
            f"(node(around:25000,{lat},{lon})[{tag}];"
            f"way(around:25000,{lat},{lon})[{tag}];);"
            "out center 100;"
        )
        for index, url in enumerate(self.urls):
            try:
                log_event(
                    self.logger,
                    "DEBUG",
                    "tool_request",
                    tool_name="places",
                    endpoint=url,
                    query=query,
                    attempt=index + 1,
                )
                response = requests.post(url, data={"data": query}, timeout=30)
                response.raise_for_status()
                data = response.json()
                elements = data.get("elements", [])
                result = {"poi_count": len(elements), "sample_names": self._sample_names(elements)}
                log_event(
                    self.logger,
                    "DEBUG",
                    "tool_response",
                    tool_name="places",
                    endpoint=url,
                    latency_ms=int((time.time() - start) * 1000),
                    response=result,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                log_event(
                    self.logger,
                    "WARN",
                    "places_endpoint_failed",
                    endpoint=url,
                    attempt=index + 1,
                    error=str(exc),
                )
                # If service is throttling or timing out, avoid hammering for the next minute.
                err = str(exc).lower()
                if "429" in err or "timeout" in err or "timed out" in err or "504" in err:
                    self.overpass_backoff_until = max(self.overpass_backoff_until, time.time() + 60)
                if index < len(self.urls) - 1:
                    time.sleep(0.4 * (index + 1))

        fallback = self._fallback_result(activity)
        log_event(
            self.logger,
            "WARN",
            "places_fallback_used",
            fallback=fallback,
        )
        return fallback

    def _activity_tag(self, activity: str | None) -> str:
        if not activity:
            return '"tourism"'
        lowered = activity.lower()
        if "ski" in lowered:
            return '"piste:type"'
        if "beach" in lowered:
            return '"natural"="beach"'
        if "museum" in lowered:
            return '"tourism"="museum"'
        return '"tourism"'

    def _sample_names(self, elements: list[dict[str, Any]]) -> list[str]:
        names = []
        for element in elements[:8]:
            tags = element.get("tags", {})
            name = tags.get("name")
            if name:
                names.append(name)
        return names

    def _fallback_result(self, activity: str | None) -> dict[str, Any]:
        if activity and "ski" in activity.lower():
            return {
                "poi_count": 3,
                "sample_names": ["Main Ski Resort", "Mountain View Point", "Snow Activity Center"],
            }
        if activity and "museum" in activity.lower():
            return {
                "poi_count": 3,
                "sample_names": ["City Museum", "Art Gallery", "History Center"],
            }
        return {
            "poi_count": 4,
            "sample_names": ["City Museum", "Old Town Center", "Central Park", "Water Park"],
        }
