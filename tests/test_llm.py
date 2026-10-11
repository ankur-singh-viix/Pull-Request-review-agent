import pytest

from app import llm

ALL_VARS = ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
            "OPENAI_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "USE_FAKE_LLM", "LLM_RPS")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ALL_VARS:
        monkeypatch.delenv(var, raising=False)


def test_no_keys_means_heuristic():
    assert llm.use_fake() and llm.describe() == "heuristic"


def test_groq_key_selects_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert not llm.use_fake()
    assert llm.describe() == "groq:llama-3.3-70b-versatile"


def test_model_override_and_fake_flag(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "my-model")
    assert llm.describe() == "groq:my-model"
    monkeypatch.setenv("USE_FAKE_LLM", "1")
    assert llm.describe() == "heuristic"


def test_priority_and_forced_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert llm.provider() == "groq"
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert llm.provider() == "openai"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("LLM_PROVIDER")
    assert llm.provider() == "anthropic"


def test_forced_provider_without_key_falls_back(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert llm.provider() == "groq"


def test_get_llm_builds_groq_client(monkeypatch):
    ChatGroq = pytest.importorskip("langchain_groq").ChatGroq

    monkeypatch.setenv("GROQ_API_KEY", "fake-key-for-test")
    assert isinstance(llm.get_llm(), ChatGroq)


def test_gemini_accepts_either_key_name(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    assert llm.provider() == "gemini"
    assert llm.describe() == "gemini:gemini-3.1-flash-lite"
    monkeypatch.delenv("GOOGLE_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert llm.provider() == "gemini"


def test_get_llm_builds_gemini_client(monkeypatch):
    ChatGoogleGenerativeAI = pytest.importorskip("langchain_google_genai").ChatGoogleGenerativeAI

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    assert isinstance(llm.get_llm(), ChatGoogleGenerativeAI)