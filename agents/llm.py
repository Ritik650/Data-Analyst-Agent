"""Thin wrapper around the Google Gemini API used by all agents.

Get a free API key at https://aistudio.google.com/apikey and set GEMINI_API_KEY.
Imports are lazy so the slim API layer / unit tests never need the SDK installed.
"""
from __future__ import annotations

import json
import os
import time

import config

_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)"
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _strip_unsupported(schema):
    """Drop JSON-Schema keys Gemini's OpenAPI-subset response_schema rejects."""
    if isinstance(schema, dict):
        return {k: _strip_unsupported(v) for k, v in schema.items()
                if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_strip_unsupported(v) for v in schema]
    return schema


def _generate(user: str, generation_config) -> str:
    """Call Gemini with backoff on free-tier rate limits; return response text."""
    from google.genai import errors

    last_error = None
    for attempt in range(5):
        try:
            response = client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=user,
                config=generation_config,
            )
            if not response.text:
                raise RuntimeError(
                    f"Gemini returned no text (feedback: {response.prompt_feedback})"
                )
            return response.text
        except errors.APIError as e:
            last_error = e
            if getattr(e, "code", None) == 429 and attempt < 4:
                time.sleep(5 * (2 ** attempt))  # free-tier RPM backoff: 5/10/20/40s
                continue
            raise
    raise last_error  # pragma: no cover


def complete(system: str, user: str, max_tokens: int = config.LLM_MAX_TOKENS) -> str:
    """Plain-text completion."""
    from google.genai import types
    return _generate(user, types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    ))


def complete_json(system: str, user: str, schema: dict,
                  max_tokens: int = config.LLM_MAX_TOKENS) -> dict:
    """Structured completion — the response is constrained to match ``schema``."""
    from google.genai import types
    text = _generate(user, types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
        response_schema=_strip_unsupported(schema),
    ))
    return json.loads(text)
