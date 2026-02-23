from __future__ import annotations

import json
import os
import time
from typing import Any

from google import genai

from src.core.logger import log_event


class GeminiClient:
    def __init__(self, logger: Any) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        self.enabled = bool(api_key)
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.logger = logger

    def generate_json(self, prompt: str, prompt_type: str) -> str:
        if not self.enabled or self.client is None:
            raise RuntimeError(
                "Missing Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your environment."
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
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        text = (response.text or "").strip()
        log_event(
            self.logger,
            "DEBUG",
            "llm_response",
            prompt_type=prompt_type,
            model=self.model_name,
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
