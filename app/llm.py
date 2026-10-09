"""LLM factory. With no API key (or USE_FAKE_LLM=1) the graph falls back to heuristics,
so tests and the CI eval gate run offline, free, and deterministic."""
import os

from langchain_core.language_models.chat_models import BaseChatModel


def use_fake() -> bool:
    if os.getenv("USE_FAKE_LLM") == "1":
        return True
    return not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


def get_llm() -> BaseChatModel:
    model = os.getenv("LLM_MODEL")
    if os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model or "claude-sonnet-5-5", temperature=0)  # type: ignore[call-arg]
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model or "gpt-4o-mini", temperature=0)
