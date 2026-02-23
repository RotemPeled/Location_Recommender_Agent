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

        if should_ask_weather_preference(parsed, memory.preferred_weather):
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
                preferred_weather=memory.preferred_weather,
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
            "preferred_weather": memory.preferred_weather,
        }
        summary = self._build_summary(llm_payload, top)

        return {
            "status": "ok",
            "summary": summary,
            "recommendations": top,
            "plan": plan,
            "parsed": asdict(parsed),
            "feedback_prompt": "What do you think about these options?",
        }

    def _build_candidates(self, parsed: Any, memory: Any) -> list[dict[str, Any]]:
        if parsed.destination:
            seeds = self.geocoding_tool.geocode(parsed.destination, limit=5)
        elif parsed.activity and parsed.activity.lower() == "skiing":
            seeds = self._geocode_seed_locations(["Innsbruck", "Aspen", "Chamonix", "Sapporo", "Queenstown"])
        else:
            seeds = self._geocode_seed_locations(["Lisbon", "Bangkok", "Tokyo", "Cape Town", "Vancouver", "Buenos Aires"])

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
                    "preferred_weather": memory.preferred_weather,
                    "estimated_flight_hours": flight_hours,
                    **weather,
                    **places,
                }
            )
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
