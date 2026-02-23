from __future__ import annotations

import json
from typing import Any


def build_intent_prompt(user_text: str) -> str:
    payload = {
        "user_text": user_text,
        "allowed_intents": [
            "destination_opinion",
            "activity_based_discovery",
            "constraint_based_discovery",
        ],
    }
    return (
        "ROLE:\n"
        "You are an intent and slot extractor for a travel assistant.\n\n"
        f"DATA:\n{json.dumps(payload, indent=2)}\n\n"
        "TASK:\n"
        "Classify the intent and extract destination, activity, travel_date_or_month, and max_flight_hours if present.\n\n"
        "RESPONSE_FORMAT (JSON ONLY):\n"
        "{\n"
        '  "intent": "destination_opinion|activity_based_discovery|constraint_based_discovery",\n'
        '  "destination": "string|null",\n'
        '  "activity": "string|null",\n'
        '  "travel_date_or_month": "string|null",\n'
        '  "max_flight_hours": "number|null"\n'
        "}"
    )


def build_activity_prompt(data: dict[str, Any]) -> str:
    return (
        "ROLE:\n"
        "You are a trip activity recommender.\n\n"
        f"DATA:\n{json.dumps(data, indent=2, default=str)}\n\n"
        "TASK:\n"
        "Provide activities possible for this trip that fit date, weather preference, and constraints.\n\n"
        "RESPONSE_FORMAT (JSON ONLY):\n"
        "{\n"
        '  "activities": [\n'
        "    {\n"
        '      "name": "string",\n'
        '      "why_fit": "string",\n'
        '      "season_match": "high|medium|low",\n'
        '      "confidence": 0.0\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def build_final_answer_prompt(data: dict[str, Any]) -> str:
    return (
        "ROLE:\n"
        "You are a travel recommendation assistant.\n\n"
        f"DATA:\n{json.dumps(data, indent=2, default=str)}\n\n"
        "TASK:\n"
        "Write a concise explanation of top recommendations and tradeoffs.\n\n"
        "RESPONSE_FORMAT (JSON ONLY):\n"
        "{\n"
        '  "summary": "string",\n'
        '  "top_recommendations": [\n'
        "    {\n"
        '      "destination": "string",\n'
        '      "why_fit": "string",\n'
        '      "confidence": 0.0\n'
        "    }\n"
        "  ]\n"
        "}"
    )
