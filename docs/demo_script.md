# Demo Script

## Setup
- Run: `pip install -r requirements.txt`
- Set env vars from `.env.example`
- Run app: `streamlit run app.py`

## Demo Flow

1. **Mandatory onboarding**
   - Enter origin city and country.
   - Show that chat is blocked until origin is saved.

2. **Prompt type 1: destination opinion**
   - Ask: "I think about going to Italy on November - what do you think?"
   - Show: reasoning plan, tool calls, ranked options.

3. **Prompt type 2: activity-based**
   - Ask: "I want to go skiing"
   - If asked, provide travel date/month and weather preference.
   - Show season-aware scoring and constraints handling.

4. **Prompt type 3: constraint-based**
   - Ask: "I want to go on a trip on 10.3.26 where should I go? not more than 4 hour flight"
   - Show flight-time filtering from fixed origin.

5. **Feedback learning**
   - Feedback: "I did not like any of these options."
   - Ask similar query again.
   - Show no-repeat behavior and new destinations.
   - Feedback: "I like the first option."
   - Show profile learning in next ranking.

6. **Debug logs**
   - Restart with `LOG_LEVEL=DEBUG` or `LOG_LEVEL=TRACE`.
   - Show terminal request/response logs for tools and LLM calls.
