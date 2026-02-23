from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from src.agent.intent_parser import IntentParser
from src.agent.planner import build_plan
from src.agent.prompt_builder import build_final_answer_prompt
from src.agent.self_correction import maybe_retry_tools, validate_candidates
from src.agent.slot_policy import missing_slots, next_clarifying_question, should_ask_weather_preference
from src.core.logger import log_event
from src.ranking.scorer import score_candidate, season_from_date_or_month


class AgentOrchestrator:
    def __init__(
        self,
        logger: Any,
        llm_client: Any,
        geocoding_tool: Any,
        weather_tool: Any,
        places_tool: Any,
        flight_tool: Any,
    ) -> None:
        self.logger = logger
        self.llm_client = llm_client
        self.intent_parser = IntentParser(llm_client, logger)
        self.geocoding_tool = geocoding_tool
        self.weather_tool = weather_tool
        self.places_tool = places_tool
        self.flight_tool = flight_tool

    def run(self, user_text: str, memory: Any) -> dict[str, Any]:
        plan = [asdict(step) for step in build_plan()]
        parsed = self.intent_parser.parse(user_text)
        parsed = self._apply_memory_context(parsed, memory)
        effective_weather_pref = self._effective_weather_preference(parsed, memory)
        log_event(self.logger, "INFO", "intent_parsed", parsed=asdict(parsed))

        missing = missing_slots(parsed)
        if missing:
            question = next_clarifying_question(missing)
            return {
                "status": "needs_clarification",
                "question": question,
                "missing_slot": missing[0],
                "plan": plan,
                "parsed": asdict(parsed),
            }

        if should_ask_weather_preference(parsed, effective_weather_pref):
            return {
                "status": "needs_weather_preference",
                "question": "Do you prefer cold, mild, warm weather, or no preference?",
                "plan": plan,
                "parsed": asdict(parsed),
            }

        candidates = self._build_candidates(parsed, memory)
        candidates = maybe_retry_tools(candidates, self.logger)
        candidates = validate_candidates(
            candidates,
            parsed.max_flight_hours,
            memory.rejected_destinations,
            self.logger,
        )

        if not candidates:
            return {
                "status": "no_results",
                "message": "I could not find fitting destinations. Could you adjust the date or constraints?",
                "plan": plan,
                "parsed": asdict(parsed),
            }

        season = season_from_date_or_month(parsed.travel_date_or_month or "")
        scored = [
            score_candidate(
                candidate=candidate,
                activity=parsed.activity,
                preferred_weather=effective_weather_pref,
                max_flight_hours=parsed.max_flight_hours,
                season=season,
                liked_profiles=memory.liked_profiles,
            )
            for candidate in candidates
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:3]

        llm_payload = {
            "intent": parsed.intent,
            "user_text": user_text,
            "top_candidates": top,
            "preferred_weather": effective_weather_pref,
        }
        summary = self._build_summary(llm_payload, top)
        detailed_message = self._build_detailed_message(summary, top)
        feedback_prompt = "What do you think about these options?"
        if len(top) == 1:
            feedback_prompt = "What do you think about this option?"
        memory.update_from_parsed(parsed)

        return {
            "status": "ok",
            "summary": detailed_message,
            "recommendations": top,
            "plan": plan,
            "parsed": asdict(parsed),
            "feedback_prompt": (
                f"{feedback_prompt} "
                "Reply with: 'like 1' or 'not good, new options'."
            ),
        }

    def _build_candidates(self, parsed: Any, memory: Any) -> list[dict[str, Any]]:
        if parsed.destination:
            seeds = self.geocoding_tool.geocode(parsed.destination, limit=2)
        elif parsed.activity and parsed.activity.lower() == "skiing":
            seeds = self._geocode_seed_locations(["Innsbruck", "Aspen", "Chamonix", "Sapporo", "Queenstown"])
        else:
            seeds = self._geocode_seed_locations(["Lisbon", "Bangkok", "Tokyo", "Cape Town", "Vancouver", "Buenos Aires"])
        if not seeds:
            log_event(
                self.logger,
                "INFO",
                "no_geocode_seeds_for_query",
                destination=parsed.destination,
                intent=parsed.intent,
            )
            return []

        candidates: list[dict[str, Any]] = []
        for seed in seeds:
            weather = self.weather_tool.fetch_weather_score(
                lat=seed["lat"],
                lon=seed["lon"],
                travel_date_or_month=parsed.travel_date_or_month,
            )
            places = self.places_tool.fetch_activity_signals(
                lat=seed["lat"],
                lon=seed["lon"],
                activity=parsed.activity,
            )
            flight_hours = self.flight_tool.estimate_hours(
                origin_city=memory.origin_city or "",
                origin_country=memory.origin_country or "",
                destination_lat=seed["lat"],
                destination_lon=seed["lon"],
            )
            candidates.append(
                {
                    "destination": seed["name"].split(",")[0],
                    "lat": seed["lat"],
                    "lon": seed["lon"],
                    "activity": parsed.activity,
                    "preferred_weather": self._effective_weather_preference(parsed, memory),
                    "estimated_flight_hours": flight_hours,
                    **weather,
                    **places,
                }
            )
        if parsed.destination and candidates:
            return candidates[:1]
        return candidates

    def _geocode_seed_locations(self, names: list[str]) -> list[dict[str, Any]]:
        output = []
        for name in names:
            rows = self.geocoding_tool.geocode(name, limit=1)
            if rows:
                output.append(rows[0])
        return output

    def _build_summary(self, payload: dict[str, Any], top: list[dict[str, Any]]) -> str:
        prompt = build_final_answer_prompt(payload)
        try:
            text = self.llm_client.generate_json(prompt, "final_summary")
            data = json.loads(text)
            return data.get("summary", "Here are the best options based on your constraints.")
        except Exception as exc:  # noqa: BLE001
            log_event(self.logger, "WARN", "summary_llm_failed", error=str(exc))
            first = top[0]
            return (
                f"Best current match is {first['destination']} with score {round(first['score'], 1)}. "
                "I also included alternatives with clear tradeoffs."
            )

    def _build_detailed_message(self, summary: str, recommendations: list[dict[str, Any]]) -> str:
        normalized_summary = self._normalize_summary_for_count(summary, len(recommendations))
        heading = "Here are quick details for each option:"
        if len(recommendations) == 1:
            heading = "Here are quick details for this option:"
        lines = [normalized_summary, "", heading]
        for index, rec in enumerate(recommendations, start=1):
            avg_temp = (float(rec.get("max_temp", 24.0)) + float(rec.get("min_temp", 14.0))) / 2.0
            condition = self._weather_condition_label(
                max_temp=float(rec.get("max_temp", 24.0)),
                min_temp=float(rec.get("min_temp", 14.0)),
                rain=float(rec.get("rain", 0.0)),
            )
            activities = rec.get("sample_names", [])[:3]
            if not activities:
                activities_text = "city center walk, local museum, food market"
            else:
                activities_text = ", ".join(activities)
            lines.append(
                (
                    f"{index}. {rec.get('destination', 'Unknown')}: "
                    f"avg weather ~{avg_temp:.1f}C, usually {condition}. "
                    f"Possible activities: {activities_text}."
                )
            )
        return "\n".join(lines)

    def _normalize_summary_for_count(self, summary: str, count: int) -> str:
        if count != 1:
            return summary
        normalized = summary
        replacements = {
            "each option": "this option",
            "these options": "this option",
            "options are": "option is",
            "options were": "option was",
            "alternatives": "alternative options",
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
            normalized = normalized.replace(old.title(), new.title())
        return normalized

    def _weather_condition_label(self, max_temp: float, min_temp: float, rain: float) -> str:
        if rain >= 4.0:
            return "rainy"
        if rain >= 1.5:
            return "cloudy"
        avg_temp = (max_temp + min_temp) / 2.0
        if avg_temp >= 12:
            return "sunny"
        return "partly cloudy"

    def _apply_memory_context(self, parsed: Any, memory: Any) -> Any:
        # Carry destination only for short follow-up answers such as a month/date.
        text = (parsed.raw_text or "").strip().lower()
        short_follow_up = len(text.split()) <= 4 and parsed.travel_date_or_month is not None
        if parsed.destination is None and short_follow_up and memory.last_destination:
            parsed.destination = memory.last_destination
        return parsed

    def _effective_weather_preference(self, parsed: Any, memory: Any) -> str | None:
        # Query-level weather intent overrides stored preference for that turn.
        activity = (parsed.activity or "").lower()
        if activity.startswith("weather_preference:cold"):
            return "cold"
        if activity.startswith("weather_preference:warm"):
            return "warm"
        if activity.startswith("weather_preference:mild"):
            return "mild"
        return memory.preferred_weather
