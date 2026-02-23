from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq

from src.core.logger import log_event


class GroqClient:
    def __init__(self, logger: Any) -> None:
        # Defensive load in case app runner didn't load env yet.
        load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)
        api_key = os.getenv("GROQ_API_KEY", "")
        self.enabled = bool(api_key)
        self.client = Groq(api_key=api_key) if api_key else None
        self.model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self.fallback_models = [
            self.model_name,
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
        ]
        self.logger = logger
        log_event(
            self.logger,
            "INFO",
            "llm_client_initialized",
            model=self.model_name,
            has_credentials=self.enabled,
        )

    def generate_json(self, prompt: str, prompt_type: str) -> str:
        if not self.enabled or self.client is None:
            raise RuntimeError(
                "Missing Groq API key. Set GROQ_API_KEY in your environment."
            )
        start = time.time()
        log_event(
            self.logger,
            "DEBUG",
            "llm_request",
            prompt_type=prompt_type,
            model=self.model_name,
            prompt=prompt,
        )
        last_error: Exception | None = None
        response = None
        used_model = self.model_name
        for candidate_model in self.fallback_models:
            try:
                response = self.client.chat.completions.create(
                    model=candidate_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                used_model = candidate_model
                if candidate_model != self.model_name:
                    log_event(
                        self.logger,
                        "WARN",
                        "llm_model_fallback_used",
                        requested_model=self.model_name,
                        fallback_model=used_model,
                    )
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                error_text = str(exc)
                if "NOT_FOUND" not in error_text and "not found" not in error_text.lower():
                    raise
        if response is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("Groq call failed with unknown error.")
        text = (response.choices[0].message.content or "").strip()
        log_event(
            self.logger,
            "DEBUG",
            "llm_response",
            prompt_type=prompt_type,
            model=used_model,
            latency_ms=int((time.time() - start) * 1000),
            response=text,
        )
        cleaned = _extract_json(text)
        return cleaned


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidate = text[first : last + 1]
        json.loads(candidate)  # validate
        return candidate
    raise ValueError("No valid JSON object in LLM response")
