"""Gemini client with deterministic fallbacks.

Used only for Agent 4 message drafting (≤1 call per recovery).
Hard wall-clock timeout — never block the recovery path on a hung LLM.
Strategy selection stays rule-based (money-safe).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

import structlog

from config import get_settings

log = structlog.get_logger()

_configured_key: str | None = None
# One worker: serialize LLM work; recovery must not pile up hung Gemini threads.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini")


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
    global _configured_key
    import google.generativeai as genai

    settings = get_settings()
    if _configured_key != settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
        _configured_key = settings.gemini_api_key
    return genai.GenerativeModel(settings.gemini_model)


def _call_with_timeout(fn, *, timeout_s: float, label: str):
    """Fail open when Gemini is slow/hung — no sleep, no retry loop."""
    future = _executor.submit(fn)
    try:
        return future.result(timeout=timeout_s)
    except FuturesTimeout:
        future.cancel()
        raise TimeoutError(f"gemini_{label}_timeout_{timeout_s}s") from None


def generate_json(prompt: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini Flash; on timeout/error return fallback instantly."""
    settings = get_settings()
    if settings.llm_provider != "gemini" or not settings.gemini_configured:
        log.info("llm_skip", reason="provider_not_gemini_or_missing_key", provider=settings.llm_provider)
        return fallback
    if not settings.llm_draft_enabled:
        log.info("llm_skip", reason="llm_draft_disabled")
        return fallback

    timeout_s = max(0.5, float(settings.llm_timeout_seconds))

    def _invoke() -> dict[str, Any]:
        response = _model().generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "response_mime_type": "application/json",
            },
            request_options={"timeout": timeout_s},
        )
        raw = (response.text or "").strip()
        return _extract_json(raw)

    try:
        data = _call_with_timeout(_invoke, timeout_s=timeout_s, label="json")
        log.info("llm_ok", model=settings.gemini_model, keys=list(data.keys()), timeout_s=timeout_s)
        return data
    except Exception as exc:
        log.warning(
            "llm_fallback",
            model=settings.gemini_model,
            rate_limited=_is_rate_limit(exc),
            timed_out=isinstance(exc, TimeoutError) or "timeout" in str(exc).lower(),
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

    timeout_s = max(0.5, float(settings.llm_timeout_seconds))

    def _invoke() -> str:
        response = _model().generate_content(
            prompt,
            generation_config={"temperature": 0.6},
            request_options={"timeout": timeout_s},
        )
        return (response.text or "").strip()

    try:
        text = _call_with_timeout(_invoke, timeout_s=timeout_s, label="text")
        return text or fallback
    except Exception as exc:
        log.warning(
            "llm_text_fallback",
            rate_limited=_is_rate_limit(exc),
            timed_out=isinstance(exc, TimeoutError) or "timeout" in str(exc).lower(),
            error=str(exc)[:300],
        )
        return fallback
