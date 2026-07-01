"""
services/llm_service.py
────────────────────────
Async Groq client wrapper.

Usage:
    from services.llm_service import chat

    response = await chat([
        {"role": "system", "content": "You are a tutor."},
        {"role": "user",   "content": "Explain binary search."},
    ])

    # JSON mode (for structured agent outputs)
    data = await chat(messages, json_mode=True)
    parsed = json.loads(data)
"""

import json
import logging

from groq import AsyncGroq

from core.config import settings

logger = logging.getLogger(__name__)

# ── Singleton client ─────────────────────────────────────────────────────────
# AsyncGroq is thread-safe and reusable across requests.
_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _client


def _model() -> str:
    """Return the configured model name. Read lazily so .env changes are picked up."""
    return settings.LLM_MODEL


# ── Core chat wrapper ────────────────────────────────────────────────────────

async def chat(messages: list[dict], json_mode: bool = False) -> str:
    """
    Call Groq chat completions and return the assistant message content.

    Args:
        messages:  OpenAI-format message list
                   [{"role": "system"|"user"|"assistant", "content": str}, ...]
        json_mode: If True, instructs the model to return valid JSON only.
                   IMPORTANT: You must also say "Return ONLY valid JSON" in
                   the system prompt, otherwise the model may still add prose.

    Returns:
        The raw string content of the assistant's reply.

    Raises:
        RuntimeError: if the Groq API returns an unexpected response.
    """
    client = get_groq_client()

    kwargs: dict = {
        "model": _model(),
        "messages": messages,
        "temperature": 0.7,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.debug("Groq request | json_mode=%s | messages=%d", json_mode, len(messages))

    response = await client.chat.completions.create(**kwargs)

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("Groq returned an empty message content.")

    logger.debug("Groq response | tokens=%s", response.usage)
    return content


async def chat_json(messages: list[dict]) -> dict:
    """
    Convenience wrapper — calls chat() in JSON mode and parses the result.

    Use for:
      - roadmap generation
      - task + MCQ generation
      - interview evaluation

    Returns:
        Parsed dict from the model's JSON response.

    Raises:
        ValueError: if the response is not valid JSON.
    """
    raw = await chat(messages, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Groq JSON parse failed. Raw response:\n%s", raw)
        raise ValueError(f"Model returned invalid JSON: {exc}") from exc
