"""Gemini client with deterministic fallbacks.

Used only for Agent 4 message drafting (≤1 call per recovery).
Strategy selection stays rule-based (money-safe). Never sleeps on 429.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from config import get_settings

log = structlog.get_logger()

_configured_key: str | None = None


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _is_rate_limit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate limit" in msg or "resource exhausted" in msg


def _model():
    """Reuse SDK config across calls (no extra network; avoids re-configure noise)."""
    global _configured_key
    import google.generativeai as genai

    settings = get_settings()
    if _configured_key != settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
        _configured_key = settings.gemini_api_key
    return genai.GenerativeModel(settings.gemini_model)


def generate_json(prompt: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini Flash; on any failure return fallback instantly (no backoff sleep)."""
    settings = get_settings()
    if settings.llm_provider != "gemini" or not settings.gemini_configured:
        log.info("llm_skip", reason="provider_not_gemini_or_missing_key", provider=settings.llm_provider)
        return fallback
    if not settings.llm_draft_enabled:
        log.info("llm_skip", reason="llm_draft_disabled")
        return fallback

    try:
        response = _model().generate_content(
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
        log.warning(
            "llm_fallback",
            model=settings.gemini_model,
            rate_limited=_is_rate_limit(exc),
            error=str(exc)[:300],
        )
        return fallback


def generate_text(prompt: str, *, fallback: str) -> str:
    settings = get_settings()
    if (
        settings.llm_provider != "gemini"
        or not settings.gemini_configured
        or not settings.llm_draft_enabled
    ):
        return fallback

    try:
        response = _model().generate_content(prompt, generation_config={"temperature": 0.6})
        text = (response.text or "").strip()
        return text or fallback
    except Exception as exc:
        log.warning(
            "llm_text_fallback",
            rate_limited=_is_rate_limit(exc),
            error=str(exc)[:300],
        )
        return fallback
