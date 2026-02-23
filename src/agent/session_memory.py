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
