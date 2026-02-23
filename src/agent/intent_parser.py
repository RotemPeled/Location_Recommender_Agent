from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dateutil import parser as date_parser

from src.agent.prompt_builder import build_intent_prompt
from src.core.logger import log_event


@dataclass
class ParsedIntent:
    intent: str
    destination: str | None = None
    activity: str | None = None
    travel_date_or_month: str | None = None
    max_flight_hours: float | None = None
    raw_text: str = ""


class IntentParser:
    ALLOWED_INTENTS = {
        "destination_opinion",
        "activity_based_discovery",
        "constraint_based_discovery",
    }

    def __init__(self, llm_client: Any, logger: Any) -> None:
        self.llm_client = llm_client
        self.logger = logger

    def parse(self, user_text: str) -> ParsedIntent:
        # Deterministic fallback first, then optionally refine with LLM.
        parsed = self._parse_with_rules(user_text)
        try:
            prompt = build_intent_prompt(user_text)
            llm_text = self.llm_client.generate_json(prompt, "intent_parser")
            llm_data = json.loads(llm_text)
            llm_intent = self._sanitize_llm_intent(llm_data.get("intent"))
            merged = ParsedIntent(
                intent=llm_intent or parsed.intent,
                destination=llm_data.get("destination") or parsed.destination,
                activity=llm_data.get("activity") or parsed.activity,
                travel_date_or_month=llm_data.get("travel_date_or_month") or parsed.travel_date_or_month,
                max_flight_hours=float(llm_data["max_flight_hours"]) if llm_data.get("max_flight_hours") is not None else parsed.max_flight_hours,
                raw_text=user_text,
            )
            return self._normalize_intent(merged)
        except Exception as exc:  # noqa: BLE001
            log_event(self.logger, "WARN", "intent_parser_llm_failed", error=str(exc))
            return self._normalize_intent(parsed)

    def _parse_with_rules(self, text: str) -> ParsedIntent:
        lowered = text.lower()
        explicit = self._extract_explicit_slots(lowered)
        activity = explicit.get("activity") or ("skiing" if "ski" in lowered else None)
        query_weather = self._extract_weather_preference_from_query(lowered)
        destination = explicit.get("destination") or self._extract_destination(lowered)
        date_or_month = explicit.get("travel_date_or_month") or self._extract_date_or_month(text)
        max_hours = explicit.get("max_flight_hours")
        if max_hours is None:
            max_hours = self._extract_max_flight_hours(lowered)
        if self._has_no_limit_phrase(lowered):
            max_hours = -1.0
        intent = self._infer_intent(
            lowered=lowered,
            destination=destination,
            activity=activity,
            max_hours=max_hours,
        )

        return ParsedIntent(
            intent=intent,
            destination=destination,
            activity=activity,
            travel_date_or_month=date_or_month,
            max_flight_hours=max_hours,
            raw_text=text,
        )

    def _infer_intent(
        self,
        lowered: str,
        destination: str | None,
        activity: str | None,
        max_hours: float | None,
    ) -> str:
        if activity is not None:
            return "activity_based_discovery"
        asks_discovery = (
            "where should i go" in lowered
            or "where to go" in lowered
            or "recommend destination" in lowered
            or "places to go" in lowered
            or "offer me places" in lowered
            or "sunny place" in lowered
            or "warm place" in lowered
        )
        has_constraint = (
            max_hours is not None
            or "not more than" in lowered
            or "max flight" in lowered
            or "within" in lowered and "hour" in lowered
        )
        if asks_discovery or (has_constraint and destination is None):
            return "constraint_based_discovery"
        return "destination_opinion"

    def _normalize_intent(self, parsed: ParsedIntent) -> ParsedIntent:
        # Guardrail: if destination is known and no flight-time constraint exists,
        # avoid constraint-based path that triggers irrelevant max-hours questions.
        if (
            parsed.intent == "constraint_based_discovery"
            and parsed.destination is not None
            and parsed.max_flight_hours is None
        ):
            parsed.intent = "destination_opinion"
        if parsed.max_flight_hours is not None and parsed.max_flight_hours < 0:
            parsed.intent = "constraint_based_discovery"
        query_weather = self._extract_weather_preference_from_query(parsed.raw_text.lower())
        if query_weather and parsed.activity is None:
            parsed.activity = f"weather_preference:{query_weather}"
        if parsed.destination and self._is_generic_destination_phrase(parsed.destination):
            parsed.destination = None
            if parsed.intent == "destination_opinion":
                parsed.intent = "constraint_based_discovery"
        if parsed.intent not in self.ALLOWED_INTENTS:
            parsed.intent = "destination_opinion"
        return parsed

    def _extract_explicit_slots(self, text: str) -> dict[str, Any]:
        slots: dict[str, Any] = {}
        patterns = {
            "destination": r"destination:\s*([^|]+)",
            "activity": r"activity:\s*([^|]+)",
            "travel_date_or_month": r"travel_date_or_month:\s*([^|]+)",
            "max_flight_hours": r"max_flight_hours:\s*([^|]+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if not match:
                continue
            value = match.group(1).strip(" .,?")
            if key == "max_flight_hours":
                try:
                    slots[key] = float(value)
                except ValueError:
                    continue
            else:
                slots[key] = value
        return slots

    def _extract_destination(self, text: str) -> str | None:
        # Non-recursive cleanup to avoid infinite recursion when fuzzy date parsing
        # returns a value not literally present in the original text.
        cleaned_text = re.sub(
            r"\|\s*travel_date_or_month:\s*[^|]+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned_text = re.sub(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            "",
            cleaned_text,
            flags=re.IGNORECASE,
        )
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()
        patterns = [r"to ([a-zA-Z\s]+)", r"going to ([a-zA-Z\s]+)", r"in ([a-zA-Z\s]+)"]
        for pattern in patterns:
            match = re.search(pattern, cleaned_text)
            if match:
                candidate = match.group(1).strip(" ?.,")
                candidate = re.sub(
                    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
                    "",
                    candidate,
                    flags=re.IGNORECASE,
                ).strip(" ,.-")
                if self._is_generic_destination_phrase(candidate):
                    return None
                if len(candidate) > 2:
                    return candidate.title()
        # Single token destination fallback (e.g., "tuscany", "crete")
        simple = cleaned_text.strip(" ?.,")
        if simple and len(simple.split()) <= 3 and all(ch.isalpha() or ch.isspace() for ch in simple):
            if not self._is_generic_destination_phrase(simple):
                return simple.title()
        return None

    def _extract_date_or_month(self, text: str) -> str | None:
        month_match = re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            text.lower(),
        )
        if month_match:
            return month_match.group(1)

        digit_match = re.search(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b", text)
        if digit_match:
            return digit_match.group(0)
        return None

    def _extract_max_flight_hours(self, text: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*hour", text)
        if not match:
            return None
        return float(match.group(1))

    def _has_no_limit_phrase(self, text: str) -> bool:
        phrases = [
            "no limit",
            "without limit",
            "without duration limitation",
            "without duration limit",
            "no duration limit",
            "no flight limit",
            "without flight limit",
        ]
        return any(phrase in text for phrase in phrases)

    def _extract_weather_preference_from_query(self, text: str) -> str | None:
        lowered = text.lower()
        if "cold place" in lowered or "cold places" in lowered or "cold weather" in lowered:
            return "cold"
        if "warm place" in lowered or "warm places" in lowered or "warm weather" in lowered:
            return "warm"
        if "mild weather" in lowered or "mild place" in lowered or "mild places" in lowered:
            return "mild"
        return None

    def _sanitize_llm_intent(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        lowered = value.strip().lower()
        if lowered in self.ALLOWED_INTENTS:
            return lowered
        for intent in self.ALLOWED_INTENTS:
            if intent in lowered:
                return intent
        return None

    def _remove_date_tokens(self, text: str, date_or_month: str) -> str:
        cleaned = text
        cleaned = re.sub(re.escape(date_or_month), "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\|\s*travel_date_or_month:\s*[^|]+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_generic_destination_phrase(self, value: str) -> bool:
        generic_tokens = {
            "place",
            "places",
            "destination",
            "somewhere",
            "anywhere",
            "sunny place",
            "warm place",
            "cold place",
        }
        lowered = value.lower().strip()
        if lowered in generic_tokens:
            return True
        return any(token in lowered for token in (" place", "destination", "somewhere", "anywhere"))
