# Location Recommender Agent

Agentic travel recommendation app built for the interview assignment.

## What this project demonstrates

- Plan-and-execute style agent flow (not plain chat)
- 2+ external tools (Nominatim, Open-Meteo, Overpass, flight estimator)
- Self-correction and no-hallucination fallback behavior
- Mandatory origin onboarding before any user query
- Feedback learning loop with no-repeat destination behavior
- Structured LLM prompt contract (Role / Data / Response format)
- Terminal debugging logs for every tool and LLM call

## Tech stack

- Python + Streamlit
- Groq API (`groq` Python SDK)
- Requests + lightweight deterministic orchestration

## Project structure

- `app.py`: Streamlit UI + onboarding + conversation flow
- `src/agent/`: orchestrator, parser, planner, prompt contract, session memory
- `src/tools/`: geocoding, weather, places, flight time estimator
- `src/ranking/`: scoring logic
- `src/core/`: terminal logging + per-turn correlation context
- `data/airports.csv`: free airport coordinates for flight-time estimates

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Copy `.env.example` values into your environment:
   - `GROQ_API_KEY`
   - optional `GROQ_MODEL`
   - optional logging config (`LOG_LEVEL`, `LOG_PRETTY`)
4. Run:
   - `streamlit run app.py`

## Mandatory origin onboarding

At startup, the assistant begins with chat-based onboarding and asks:
- origin city is provided
- origin country is provided

This ensures flight constraints are always computed from a fixed origin.

## Prompt contract (clean LLM I/O)

Every LLM request uses:
1. **Role**
2. **Data** (JSON payload)
3. **Response format** (strict JSON schema)

Invalid JSON responses trigger one repair path and fallback behavior.

## Scoring model

- `activity_fit` (0-40), season/date-aware
- `weather_fit` (0-30), aligned with user weather preference
- `flight_feasibility` (0-20), respects max flight hours when provided
- `diversity_novelty` (0-10), reduces repetitive recommendations

If no explicit activity is requested, activity fit becomes "things-to-do fit" for that season.

## Feedback learning loop

After recommendations:
- If user says they like an option: store a preference profile
- If user rejects all options: mark shown destinations as rejected
- Next recommendation run excludes rejected destinations

## Logging and debugging

Terminal logs include request/response traces for each tool and LLM call.

- `LOG_LEVEL=INFO` default
- `LOG_LEVEL=DEBUG` for metadata-level traces
- `LOG_LEVEL=TRACE` for full payload traces
- Per-turn correlation IDs group logs for one user request

## Free API usage notes

- Nominatim and Overpass should be used politely (rate-conscious usage).
- This project includes a custom user agent for Nominatim.
- No paid travel data source is required for the baseline demo.

## Demo

Use `docs/demo_script.md` to record the requested walkthrough video.