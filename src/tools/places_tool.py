from __future__ import annotations

import time
from typing import Any

import requests

from src.core.logger import log_event


class PlacesTool:
    def __init__(self, logger: Any) -> None:
        self.logger = logger
        self.url = "https://overpass-api.de/api/interpreter"

    def fetch_activity_signals(self, lat: float, lon: float, activity: str | None) -> dict[str, Any]:
        start = time.time()
        tag = self._activity_tag(activity)
        query = (
            "[out:json][timeout:25];"
            f"(node(around:25000,{lat},{lon})[{tag}];"
            f"way(around:25000,{lat},{lon})[{tag}];);"
            "out center 100;"
        )
        log_event(self.logger, "DEBUG", "tool_request", tool_name="places", query=query)
        response = requests.post(self.url, data={"data": query}, timeout=30)
        response.raise_for_status()
        data = response.json()
        elements = data.get("elements", [])
        result = {"poi_count": len(elements), "sample_names": self._sample_names(elements)}
        log_event(
            self.logger,
            "DEBUG",
            "tool_response",
            tool_name="places",
            latency_ms=int((time.time() - start) * 1000),
            response=result,
        )
        return result

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
