from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

from src.agent.llm_client import GeminiClient
from src.agent.orchestrator import AgentOrchestrator
from src.agent.session_memory import SessionMemory
from src.core.logger import setup_logger
from src.core.logging_context import start_new_turn
from src.tools.flight_time_estimator import FlightTimeEstimator
from src.tools.geocoding_tool import GeocodingTool
from src.tools.places_tool import PlacesTool
from src.tools.weather_tool import WeatherTool


st.set_page_config(page_title="Location Recommender Agent", layout="wide")
st.title("Location Recommender Agent")
st.caption("Agentic travel assistant with tools, self-correction, and feedback learning")


def init_state() -> None:
    if "memory" not in st.session_state:
        st.session_state.memory = SessionMemory()
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "logger" not in st.session_state:
        st.session_state.logger = setup_logger()
    if "pending_weather_question" not in st.session_state:
        st.session_state.pending_weather_question = False
    if "pending_clarification_slot" not in st.session_state:
        st.session_state.pending_clarification_slot = None
    if "draft_query" not in st.session_state:
        st.session_state.draft_query = None
    if "last_query" not in st.session_state:
        st.session_state.last_query = None
    if "onboarding_prompted" not in st.session_state:
        st.session_state.onboarding_prompted = False
    if "orchestrator" not in st.session_state:
        logger = st.session_state.logger
        llm_client = GeminiClient(logger)
        geocoding_tool = GeocodingTool(logger)
        weather_tool = WeatherTool(logger)
        places_tool = PlacesTool(logger)
        flight_tool = FlightTimeEstimator(str(ROOT / "data" / "airports.csv"))
        st.session_state.orchestrator = AgentOrchestrator(
            logger=logger,
            llm_client=llm_client,
            geocoding_tool=geocoding_tool,
            weather_tool=weather_tool,
            places_tool=places_tool,
            flight_tool=flight_tool,
        )


def handle_chat_onboarding(
    user_input: str,
    memory: SessionMemory,
    orchestrator: AgentOrchestrator,
) -> bool:
    # Returns True when message was consumed by onboarding flow.
    if memory.has_origin():
        return False

    if "," not in user_input:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Please provide your origin in this exact format: city, country (example: Tel Aviv, Israel).",
            }
        )
        return True

    city, country = [part.strip() for part in user_input.split(",", 1)]
    if not city or not country:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Both city and country are required. Please send: city, country.",
            }
        )
        return True

    rows = orchestrator.geocoding_tool.geocode(f"{city}, {country}", limit=3)
    if not rows:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "I could not validate that city/country pair. "
                    "Please try again in the format: city, country."
                ),
            }
        )
        return True

    top_name = rows[0].get("name", "").lower()
    if city.lower() not in top_name or country.lower() not in top_name:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    "I found a location, but it does not confidently match both city and country. "
                    "Please provide a clearer pair, for example: Florence, Italy."
                ),
            }
        )
        return True

    memory.set_origin(city, country)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": (
                f"Origin saved: {memory.origin_city}, {memory.origin_country}. "
                "Now ask me where to travel."
            ),
        }
    )
    return True


def apply_feedback(memory: SessionMemory, feedback_text: str, recommendations: list[dict]) -> None:
    lowered = feedback_text.lower()
    if "didn't like" in lowered or "did not like" in lowered or "none" in lowered:
        memory.add_rejections([row["destination"] for row in recommendations])
    if "like the first" in lowered and recommendations:
        first = recommendations[0]
        memory.add_like_profile(
            {
                "destination": first["destination"],
                "activity": first.get("activity"),
                "preferred_weather": memory.preferred_weather,
            }
        )


def capture_weather_preference(memory: SessionMemory, user_text: str) -> bool:
    lowered = user_text.lower()
    if "cold" in lowered:
        memory.preferred_weather = "cold"
        return True
    if "mild" in lowered:
        memory.preferred_weather = "mild"
        return True
    if "warm" in lowered:
        memory.preferred_weather = "warm"
        return True
    if "no" in lowered and "preference" in lowered:
        memory.preferred_weather = "no_preference"
        return True
    return False


def is_feedback_text(user_text: str) -> bool:
    lowered = user_text.lower()
    return (
        "like the first" in lowered
        or "didn't like" in lowered
        or "did not like" in lowered
        or "none of" in lowered
    )


def main() -> None:
    init_state()
    memory: SessionMemory = st.session_state.memory
    orchestrator: AgentOrchestrator = st.session_state.orchestrator

    if not memory.has_origin() and not st.session_state.onboarding_prompted:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Before we start, please provide your origin as: city, country (example: Tel Aviv, Israel).",
            }
        )
        st.session_state.onboarding_prompted = True

    with st.sidebar:
        st.header("Session Profile")
        if memory.has_origin():
            st.write(f"Origin: **{memory.origin_city}, {memory.origin_country}**")
        else:
            st.write("Origin: **Not set yet**")
        st.write(f"Preferred weather: **{memory.preferred_weather or 'Not set'}**")
        st.write(f"Rejected destinations: **{len(memory.rejected_destinations)}**")
        st.write(f"Liked profiles: **{len(memory.liked_profiles)}**")
        st.divider()
        st.caption("Logs")
        st.code(
            "Set LOG_LEVEL=DEBUG or TRACE in terminal to print request/response logs "
            "for each tool and LLM call."
        )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("data"):
                st.json(msg["data"])

    if memory.has_origin():
        prompt_text = "Ask your travel question"
    else:
        prompt_text = "Enter your origin as: city, country"
    user_input = st.chat_input(prompt_text)
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        if handle_chat_onboarding(user_input, memory, orchestrator):
            st.rerun()

        if st.session_state.get("last_recommendations") and is_feedback_text(user_input):
            apply_feedback(memory, user_input, st.session_state.last_recommendations)
            st.session_state.messages.append(
                {"role": "assistant", "content": "Thanks, I learned from your feedback."}
            )
            if (
                "didn't like" in user_input.lower()
                or "did not like" in user_input.lower()
                or "none of" in user_input.lower()
            ):
                # Regenerate with anti-repeat filter using same last query.
                original_query = st.session_state.last_query
                if original_query:
                    start_new_turn()
                    retry = orchestrator.run(original_query, memory)
                    if retry["status"] == "ok":
                        st.session_state.last_recommendations = retry["recommendations"]
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": "I generated new options and excluded the previous destinations.",
                                "data": {"recommendations": retry["recommendations"]},
                            }
                        )
                        st.session_state.messages.append(
                            {"role": "assistant", "content": retry["feedback_prompt"]}
                        )
                    else:
                        st.session_state.messages.append(
                            {"role": "assistant", "content": "I need one more detail before regenerating options."}
                        )
            st.rerun()

        if st.session_state.pending_clarification_slot:
            slot = st.session_state.pending_clarification_slot
            base = st.session_state.draft_query or ""
            combined = f"{base} | {slot}: {user_input}"
            st.session_state.pending_clarification_slot = None
            st.session_state.draft_query = None
            user_input = combined
        if st.session_state.pending_weather_question:
            if capture_weather_preference(memory, user_input):
                st.session_state.pending_weather_question = False
                st.session_state.messages.append(
                    {"role": "assistant", "content": "Got it. I saved your weather preference."}
                )
                if st.session_state.draft_query:
                    user_input = st.session_state.draft_query
                    st.session_state.draft_query = None
                else:
                    st.rerun()
            else:
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": "Please answer with: cold, mild, warm, or no preference.",
                    }
                )
                st.rerun()

        start_new_turn()
        result = orchestrator.run(user_input, memory)
        if result["status"] == "needs_weather_preference":
            st.session_state.pending_weather_question = True
            st.session_state.draft_query = user_input
            st.session_state.messages.append(
                {"role": "assistant", "content": result["question"]}
            )
        elif result["status"] == "needs_clarification":
            st.session_state.pending_clarification_slot = result.get("missing_slot")
            st.session_state.draft_query = user_input
            st.session_state.messages.append(
                {"role": "assistant", "content": result["question"], "data": result["parsed"]}
            )
        elif result["status"] == "no_results":
            st.session_state.messages.append(
                {"role": "assistant", "content": result["message"], "data": result["parsed"]}
            )
        else:
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result["summary"],
                    "data": {
                        "plan": result["plan"],
                        "recommendations": result["recommendations"],
                    },
                }
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": result["feedback_prompt"]}
            )
            st.session_state.last_recommendations = result["recommendations"]
            st.session_state.last_query = user_input
        st.rerun()

    if st.session_state.messages:
        last = st.session_state.messages[-1]
        if last["role"] == "assistant" and "feedback_prompt" in last.get("content", "").lower():
            st.caption("Use chat to provide feedback. Example: 'I like the first option' or 'I didn't like any'.")

    if st.session_state.get("last_recommendations"):
        with st.expander("Submit feedback quickly"):
            feedback = st.text_input("Feedback on latest recommendations")
            if st.button("Save feedback"):
                if feedback.strip():
                    apply_feedback(memory, feedback, st.session_state.last_recommendations)
                    st.success("Feedback saved to session memory.")

    with st.expander("Debug: session memory"):
        st.json(
            {
                "origin_city": memory.origin_city,
                "origin_country": memory.origin_country,
                "preferred_weather": memory.preferred_weather,
                "rejected_destinations": sorted(memory.rejected_destinations),
                "liked_profiles": memory.liked_profiles,
            }
        )


if __name__ == "__main__":
    os.environ.setdefault("LOG_LEVEL", "INFO")
    main()
