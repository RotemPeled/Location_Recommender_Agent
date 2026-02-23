from __future__ import annotations

import datetime as dt
import time
from typing import Any

import requests
from requests import HTTPError

from src.core.logger import log_event


class WeatherTool:
    def __init__(self, logger: Any) -> None:
        self.logger = logger
        self.url = "https://api.open-meteo.com/v1/forecast"

    def fetch_weather_score(self, lat: float, lon: float, travel_date_or_month: str) -> dict[str, Any]:
        start = time.time()
        target_date = self._normalize_date(travel_date_or_month)
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "start_date": target_date,
            "end_date": target_date,
        }
        log_event(self.logger, "DEBUG", "tool_request", tool_name="weather", params=params)
        try:
            response = requests.get(self.url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})
            max_temp = float(daily.get("temperature_2m_max", [25])[0])
            min_temp = float(daily.get("temperature_2m_min", [15])[0])
            rain = float(daily.get("precipitation_sum", [0])[0])
        except HTTPError as exc:
            fallback = self._seasonal_fallback(travel_date_or_month)
            log_event(
                self.logger,
                "WARN",
                "weather_fallback_used",
                reason="forecast_endpoint_unavailable_for_date",
                status_code=getattr(exc.response, "status_code", None),
                target_date=target_date,
                fallback=fallback,
            )
            max_temp = fallback["max_temp"]
            min_temp = fallback["min_temp"]
            rain = fallback["rain"]
        except Exception as exc:  # noqa: BLE001
            fallback = self._seasonal_fallback(travel_date_or_month)
            log_event(
                self.logger,
                "WARN",
                "weather_fallback_used",
                reason=str(exc),
                target_date=target_date,
                fallback=fallback,
            )
            max_temp = fallback["max_temp"]
            min_temp = fallback["min_temp"]
            rain = fallback["rain"]

        log_event(
            self.logger,
            "DEBUG",
            "tool_response",
            tool_name="weather",
            latency_ms=int((time.time() - start) * 1000),
            response={"max_temp": max_temp, "min_temp": min_temp, "rain": rain},
        )
        return {"max_temp": max_temp, "min_temp": min_temp, "rain": rain}

    def _normalize_date(self, value: str) -> str:
        months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        lowered = value.lower().strip()
        if lowered in months:
            year = dt.date.today().year
            return dt.date(year, months[lowered], 15).isoformat()
        for fmt in ("%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(value, fmt)
                return parsed.date().isoformat()
            except ValueError:
                continue
        # Support day-month inputs like 10.3 (assume current year).
        try:
            dm = dt.datetime.strptime(value, "%d.%m")
            year = dt.date.today().year
            return dt.date(year, dm.month, dm.day).isoformat()
        except ValueError:
            pass
        return dt.date.today().isoformat()

    def _seasonal_fallback(self, value: str) -> dict[str, float]:
        month = self._month_from_input(value)
        if month in (12, 1, 2):
            return {"max_temp": 12.0, "min_temp": 5.0, "rain": 3.5}
        if month in (3, 4, 5):
            return {"max_temp": 19.0, "min_temp": 10.0, "rain": 2.0}
        if month in (6, 7, 8):
            return {"max_temp": 30.0, "min_temp": 21.0, "rain": 0.8}
        return {"max_temp": 23.0, "min_temp": 14.0, "rain": 1.7}

    def _month_from_input(self, value: str) -> int:
        lowered = (value or "").lower().strip()
        by_name = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        if lowered in by_name:
            return by_name[lowered]
        for fmt in ("%d.%m.%y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(value, fmt).month
            except ValueError:
                continue
        return dt.date.today().month
