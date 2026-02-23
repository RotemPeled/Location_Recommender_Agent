from __future__ import annotations

from typing import Any


REQUIRED_SLOTS_BY_INTENT = {
    "destination_opinion": ["destination", "travel_date_or_month"],
    "activity_based_discovery": ["activity", "travel_date_or_month"],
    "constraint_based_discovery": ["travel_date_or_month", "max_flight_hours"],
}


def missing_slots(parsed_intent: Any) -> list[str]:
    required = REQUIRED_SLOTS_BY_INTENT.get(parsed_intent.intent, [])
    missing = []
    for slot in required:
        if getattr(parsed_intent, slot, None) in (None, ""):
            missing.append(slot)
    return missing


def next_clarifying_question(missing: list[str]) -> str:
    if not missing:
        return ""
    slot = missing[0]
    if slot == "travel_date_or_month":
        return "What date or month are you planning to travel?"
    if slot == "destination":
        return "Which destination are you considering?"
    if slot == "activity":
        return "Which activity are you most interested in?"
    if slot == "max_flight_hours":
        return "What is your maximum flight duration in hours?"
    return f"Could you provide: {slot}?"


def should_ask_weather_preference(parsed_intent: Any, preferred_weather: str | None) -> bool:
    if preferred_weather:
        return False
    if parsed_intent.activity and parsed_intent.activity.lower() == "skiing":
        return False
    return True
