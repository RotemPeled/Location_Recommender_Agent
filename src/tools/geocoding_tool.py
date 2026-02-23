from __future__ import annotations

import time
from typing import Any

import requests

from src.core.logger import log_event


class GeocodingTool:
    def __init__(self, logger: Any) -> None:
        self.logger = logger
        self.url = "https://nominatim.openstreetmap.org/search"
        self.headers = {"User-Agent": "LocationRecommenderAgent/1.0"}

    def geocode(self, place: str, limit: int = 5) -> list[dict[str, Any]]:
        start = time.time()
        params = {
            "q": place,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
            "accept-language": "en",
        }
        log_event(self.logger, "DEBUG", "tool_request", tool_name="geocoding", params=params)
        response = requests.get(self.url, params=params, headers=self.headers, timeout=20)
        response.raise_for_status()
        rows = response.json()
        result = [
            {
                "name": row.get("display_name", ""),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "address": row.get("address", {}),
                "country_code": row.get("address", {}).get("country_code", ""),
            }
            for row in rows
        ]
        log_event(
            self.logger,
            "DEBUG",
            "tool_response",
            tool_name="geocoding",
            latency_ms=int((time.time() - start) * 1000),
            count=len(result),
            response=result,
        )
        return result
