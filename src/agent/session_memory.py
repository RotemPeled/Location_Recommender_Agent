from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionMemory:
    origin_city: str | None = None
    origin_country: str | None = None
    preferred_weather: str | None = None
    rejected_destinations: set[str] = field(default_factory=set)
    liked_profiles: list[dict[str, Any]] = field(default_factory=list)
    last_destination: str | None = None
    last_travel_date_or_month: str | None = None
    last_activity: str | None = None
    last_max_flight_hours: float | None = None

    def set_origin(self, city: str, country: str) -> None:
        self.origin_city = city.strip()
        self.origin_country = country.strip()

    def add_rejections(self, destinations: list[str]) -> None:
        for destination in destinations:
            self.rejected_destinations.add(destination.lower())

    def add_like_profile(self, profile: dict[str, Any]) -> None:
        self.liked_profiles.append(profile)

    def has_origin(self) -> bool:
        return bool(self.origin_city and self.origin_country)

    def update_from_parsed(self, parsed: Any) -> None:
        if getattr(parsed, "destination", None):
            self.last_destination = parsed.destination
        if getattr(parsed, "travel_date_or_month", None):
            self.last_travel_date_or_month = parsed.travel_date_or_month
        if getattr(parsed, "activity", None):
            self.last_activity = parsed.activity
        if getattr(parsed, "max_flight_hours", None) is not None:
            self.last_max_flight_hours = parsed.max_flight_hours
