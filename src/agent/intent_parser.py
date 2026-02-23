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
            merged = ParsedIntent(
                intent=llm_data.get("intent", parsed.intent),
                destination=llm_data.get("destination") or parsed.destination,
                activity=llm_data.get("activity") or parsed.activity,
                travel_date_or_month=llm_data.get("travel_date_or_month") or parsed.travel_date_or_month,
                max_flight_hours=float(llm_data["max_flight_hours"]) if llm_data.get("max_flight_hours") is not None else parsed.max_flight_hours,
                raw_text=user_text,
            )
            return merged
        except Exception as exc:  # noqa: BLE001
            log_event(self.logger, "WARN", "intent_parser_llm_failed", error=str(exc))
            return parsed

    def _parse_with_rules(self, text: str) -> ParsedIntent:
        lowered = text.lower()
        explicit = self._extract_explicit_slots(lowered)
        intent = "destination_opinion"
        if "ski" in lowered:
            intent = "activity_based_discovery"
        if "where should i go" in lowered or "not more than" in lowered or "max" in lowered:
            intent = "constraint_based_discovery"

        activity = explicit.get("activity") or ("skiing" if "ski" in lowered else None)
        destination = explicit.get("destination") or self._extract_destination(lowered)
        date_or_month = explicit.get("travel_date_or_month") or self._extract_date_or_month(text)
        max_hours = explicit.get("max_flight_hours") or self._extract_max_flight_hours(lowered)

        return ParsedIntent(
            intent=intent,
            destination=destination,
            activity=activity,
            travel_date_or_month=date_or_month,
            max_flight_hours=max_hours,
            raw_text=text,
        )

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
        patterns = [r"to ([a-zA-Z\s]+)", r"going to ([a-zA-Z\s]+)", r"in ([a-zA-Z\s]+)"]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1).strip(" ?.,")
                if len(candidate) > 2:
                    return candidate.title()
        return None

    def _extract_date_or_month(self, text: str) -> str | None:
        month_match = re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            text.lower(),
        )
        if month_match:
            return month_match.group(1)

        digit_match = re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", text)
        if digit_match:
            return digit_match.group(0)

        try:
            dt = date_parser.parse(text, fuzzy=True, dayfirst=True)
            if dt.year >= datetime.now().year:
                return dt.strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            return None
        return None

    def _extract_max_flight_hours(self, text: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*hour", text)
        if not match:
            return None
        return float(match.group(1))
