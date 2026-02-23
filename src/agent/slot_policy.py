from __future__ import annotations

from typing import Any


REQUIRED_SLOTS_BY_INTENT = {
    "destination_opinion": ["destination", "travel_date_or_month"],
    "activity_based_discovery": ["activity", "travel_date_or_month"],
    # Flight duration is optional unless explicitly requested by user.
    "constraint_based_discovery": ["travel_date_or_month"],
}


def missing_slots(parsed_intent: Any) -> list[str]:
    required = list(REQUIRED_SLOTS_BY_INTENT.get(parsed_intent.intent, []))
    if getattr(parsed_intent, "max_flight_hours", None) == -1:
        required = [slot for slot in required if slot != "max_flight_hours"]
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
