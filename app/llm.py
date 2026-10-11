"""LLM factory. With no API key (or USE_FAKE_LLM=1) the graph falls back to heuristics,
so tests and the CI eval gate run offline, free, and deterministic.

Providers: anthropic, groq (free tier), gemini (free tier), openai. Set LLM_PROVIDER to force
one; otherwise the first key found wins. LLM_MODEL overrides the default model. LLM_RPS
throttles requests per second, which free tiers need (for example LLM_RPS=0.15).
LLM_VERIFY_MODEL runs the verification pass on a different (stronger) model.
"""
import os
from functools import lru_cache
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter

DEFAULTS = {
    "anthropic": "claude-sonnet-5-5",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-3.1-flash-lite",
    "openai": "gpt-4o-mini",
}
KEYS = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
}


def _key(name: str) -> str | None:
    for var in KEYS[name]:
        if value := os.getenv(var):
            return value
    return None


def provider() -> str | None:
    forced = os.getenv("LLM_PROVIDER", "").lower()
    if forced in KEYS and _key(forced):
        return forced
    for name in KEYS:
        if _key(name):
            return name
    return None


def use_fake() -> bool:
    return os.getenv("USE_FAKE_LLM") == "1" or provider() is None


def describe() -> str:
    """Human-readable label for eval reports."""
    p = provider()
    if use_fake() or p is None:
        return "heuristic"
    label = f"{p}:{os.getenv('LLM_MODEL') or DEFAULTS[p]}"
    verifier = os.getenv("LLM_VERIFY_MODEL")
    return f"{label} verifier={verifier}" if verifier else label


@lru_cache(maxsize=1)
def _rate_limiter() -> InMemoryRateLimiter | None:
    # One shared limiter, because the four reviewers call the model in parallel.
    rps = float(os.getenv("LLM_RPS") or 0)
    return InMemoryRateLimiter(requests_per_second=rps, max_bucket_size=1) if rps > 0 else None


def get_llm(model: str | None = None) -> BaseChatModel:
    p = provider()
    model = model or os.getenv("LLM_MODEL") or DEFAULTS.get(p or "", "")
    common: dict[str, Any] = {"temperature": 0, "max_retries": 6, "rate_limiter": _rate_limiter()}
    if p == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, **common)  # type: ignore[call-arg]
    if p == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, **common)  # type: ignore[call-arg]
    if p == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=_key("gemini"), **common)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, **common)