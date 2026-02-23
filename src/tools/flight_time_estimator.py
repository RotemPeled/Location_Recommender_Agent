from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


class FlightTimeEstimator:
    def __init__(self, data_path: str) -> None:
        self.airports = self._load_airports(data_path)

    def estimate_hours(
        self,
        origin_city: str,
        origin_country: str,
        destination_lat: float,
        destination_lon: float,
    ) -> float | None:
        origin = self._find_airport(origin_city, origin_country)
        if not origin:
            return None
        distance_km = self._haversine_km(
            origin["lat"],
            origin["lon"],
            destination_lat,
            destination_lon,
        )
        return round((distance_km / 800.0) + 0.6, 2)

    def _load_airports(self, path: str) -> list[dict[str, Any]]:
        airports = []
        csv_path = Path(path)
        if not csv_path.exists():
            return airports
        with csv_path.open("r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                airports.append(
                    {
                        "city": row["city"].lower(),
                        "country": row["country"].lower(),
                        "lat": float(row["lat"]),
                        "lon": float(row["lon"]),
                    }
                )
        return airports

    def _find_airport(self, city: str, country: str) -> dict[str, Any] | None:
        city = city.lower().strip()
        country = country.lower().strip()
        for airport in self.airports:
            if airport["city"] == city and airport["country"] == country:
                return airport
        for airport in self.airports:
            if airport["city"] == city:
                return airport
        return None

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c
