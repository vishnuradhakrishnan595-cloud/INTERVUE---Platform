"""Optional LLM access. Everything in the platform works without it (heuristic fallbacks)."""
import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


def llm_available() -> bool:
    return bool(getattr(settings, "ANTHROPIC_API_KEY", ""))


def llm_json(system: str, prompt: str, max_tokens: int = 1500):
    """Ask the LLM for a JSON answer. Returns parsed JSON or None on any failure."""
    if not llm_available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system + "\nRespond with valid JSON only, no prose and no markdown fences.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
        return json.loads(text)
    except Exception:  # network, auth, parse errors -> caller falls back to heuristics
        logger.exception("LLM call failed; using heuristic fallback")
        return None
