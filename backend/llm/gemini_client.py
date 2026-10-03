"""Gemini client with deterministic fallbacks.

Used for Agent 3 reasoning enrichment + Agent 4 message drafting.
Strategy selection itself stays rule-based (money-safe).
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from config import get_settings

log = structlog.get_logger()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def generate_json(prompt: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini Flash; on any failure return fallback (never block recovery)."""
    settings = get_settings()
    if settings.llm_provider != "gemini" or not settings.gemini_configured:
        log.info("llm_skip", reason="provider_not_gemini_or_missing_key", provider=settings.llm_provider)
        return fallback

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "response_mime_type": "application/json",
            },
        )
        raw = (response.text or "").strip()
        data = _extract_json(raw)
        log.info("llm_ok", model=settings.gemini_model, keys=list(data.keys()))
        return data
    except Exception as exc:
        log.warning("llm_fallback", model=settings.gemini_model, error=str(exc))
        return fallback


def generate_text(prompt: str, *, fallback: str) -> str:
    settings = get_settings()
    if settings.llm_provider != "gemini" or not settings.gemini_configured:
        return fallback

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        response = model.generate_content(prompt, generation_config={"temperature": 0.6})
        text = (response.text or "").strip()
        return text or fallback
    except Exception as exc:
        log.warning("llm_text_fallback", error=str(exc))
        return fallback
