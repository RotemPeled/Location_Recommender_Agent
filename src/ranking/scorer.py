from __future__ import annotations

from typing import Any


def season_from_date_or_month(travel_date_or_month: str) -> str:
    lower = travel_date_or_month.lower()
    winter = {"december", "january", "february"}
    spring = {"march", "april", "may"}
    summer = {"june", "july", "august"}
    autumn = {"september", "october", "november"}
    if lower in winter:
        return "winter"
    if lower in spring:
        return "spring"
    if lower in summer:
        return "summer"
    if lower in autumn:
        return "autumn"
    # Numeric dates fallback.
    try:
        parts = travel_date_or_month.replace("-", ".").split(".")
        month = int(parts[1])
    except Exception:  # noqa: BLE001
        return "unknown"
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


def score_candidate(
    candidate: dict[str, Any],
    activity: str | None,
    preferred_weather: str | None,
    max_flight_hours: float | None,
    season: str,
    liked_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    activity_fit = _activity_score(candidate, activity, season)
    weather_fit = _weather_score(candidate, preferred_weather)
    flight_fit = _flight_score(candidate, max_flight_hours)
    diversity = _diversity_score(candidate)
    like_bonus = _like_similarity_bonus(candidate, liked_profiles)

    total = activity_fit + weather_fit + flight_fit + diversity + like_bonus
    candidate["score_breakdown"] = {
        "activity_fit": activity_fit,
        "weather_fit": weather_fit,
        "flight_feasibility": flight_fit,
        "diversity_novelty": diversity,
        "like_bonus": like_bonus,
        "total": total,
    }
    candidate["score"] = total
    return candidate


def _activity_score(candidate: dict[str, Any], activity: str | None, season: str) -> float:
    poi_count = candidate.get("poi_count", 0)
    base = min(40.0, poi_count / 5.0)
    if not activity:
        return base
    if activity.lower() == "skiing":
        if season == "winter":
            return min(40.0, base + 12.0)
        return max(5.0, base - 15.0)
    return base


def _weather_score(candidate: dict[str, Any], preferred_weather: str | None) -> float:
    max_temp = candidate.get("max_temp", 24.0)
    min_temp = candidate.get("min_temp", 14.0)
    rain = candidate.get("rain", 0.0)
    avg = (max_temp + min_temp) / 2
    score = 20.0 - min(10.0, rain * 1.2)
    pref = (preferred_weather or "no_preference").lower()
    if pref == "cold":
        score += max(0.0, 10 - abs(avg - 8))
    elif pref == "mild":
        score += max(0.0, 10 - abs(avg - 18))
    elif pref == "warm":
        score += max(0.0, 10 - abs(avg - 27))
    else:
        score += 6.0
    return max(0.0, min(30.0, score))


def _flight_score(candidate: dict[str, Any], max_flight_hours: float | None) -> float:
    est = candidate.get("estimated_flight_hours")
    if est is None:
        return 8.0
    if max_flight_hours is None:
        return max(0.0, min(20.0, 20.0 - est * 1.6))
    if est <= max_flight_hours:
        return 20.0
    return max(0.0, 20.0 - (est - max_flight_hours) * 8.0)


def _diversity_score(candidate: dict[str, Any]) -> float:
    return min(10.0, 5.0 + len(set(candidate.get("sample_names", []))) / 2.0)


def _like_similarity_bonus(candidate: dict[str, Any], liked_profiles: list[dict[str, Any]]) -> float:
    if not liked_profiles:
        return 0.0
    # Basic bonus if destination shares weather/activity profile with past liked options.
    current_activity = candidate.get("activity")
    current_weather = candidate.get("preferred_weather")
    for profile in liked_profiles:
        if profile.get("activity") == current_activity or profile.get("preferred_weather") == current_weather:
            return 3.0
    return 0.0
