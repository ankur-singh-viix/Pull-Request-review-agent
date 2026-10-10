"""LLM factory. With no API key (or USE_FAKE_LLM=1) the graph falls back to heuristics,
so tests and the CI eval gate run offline, free, and deterministic."""
import os

from langchain_core.language_models.chat_models import BaseChatModel

DEFAULT_ANTHROPIC = "claude-sonnet-5-5"
DEFAULT_OPENAI = "gpt-4o-mini"


def use_fake() -> bool:
    if os.getenv("USE_FAKE_LLM") == "1":
        return True
    return not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


def describe() -> str:
    """Human-readable label for eval reports."""
    if use_fake():
        return "heuristic"
    if os.getenv("ANTHROPIC_API_KEY"):
        return f"anthropic:{os.getenv('LLM_MODEL') or DEFAULT_ANTHROPIC}"
    return f"openai:{os.getenv('LLM_MODEL') or DEFAULT_OPENAI}"


def get_llm() -> BaseChatModel:
    model = os.getenv("LLM_MODEL")
    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model or DEFAULT_ANTHROPIC, temperature=0)  # type: ignore[call-arg]
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model or DEFAULT_OPENAI, temperature=0)