import pytest
from langchain_core.runnables import RunnableLambda

from app import nodes
from app.rag import build_query, get_retriever, load_guidelines
from app.state import Finding, Findings


def _diff(line: str, path: str = "app/x.py") -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,1 @@\n+{line}\n"


def test_guidelines_load_with_unique_ids_and_categories():
    docs = load_guidelines()
    ids = [d.metadata["rule_id"] for d in docs]
    assert len(ids) >= 15 and len(ids) == len(set(ids))
    assert {d.metadata["category"] for d in docs} == {"security", "bug", "style", "tests"}


@pytest.mark.parametrize("line,expected", [
    ("logger = logging.getLogger(__name__)", "STY-4"),
    ("data = request.get_json()", "REL-5"),
    ('return {"error": str(e)}, 400', "REL-6"),
    ('requests.get("http://billing.internal/api/x")', "SEC-6"),
    ("obj = pickle.loads(request.body)", "SEC-4"),
    ("hashed = hashlib.md5(password.encode()).hexdigest()", "SEC-5"),
])
def test_retrieval_finds_relevant_rule(line, expected):
    docs = get_retriever().invoke(build_query(_diff(line), []))
    top3 = [d.metadata["rule_id"] for d in docs[:3]]
    assert expected in top3, top3


def test_retrieve_node_and_toggle(monkeypatch):
    state = {"diff": _diff("data = request.get_json()"), "change_types": ["backend"]}
    out = nodes.retrieve_guidelines(state)
    assert out["guidelines"] and {"rule_id", "category", "text"} <= set(out["guidelines"][0])
    monkeypatch.setenv("USE_GUIDELINES", "0")
    assert nodes.retrieve_guidelines(state) == {"guidelines": []}


def test_llm_prompt_includes_rules_and_drops_hallucinated_ids(monkeypatch):
    seen = {}

    class FakeLLM:
        def with_structured_output(self, schema):
            def respond(prompt_value):
                seen["prompt"] = prompt_value.to_string()
                return Findings(findings=[
                    Finding(category="x", severity="high", file="app/x.py", line=1,
                            message="real rule", rule="SEC-6"),
                    Finding(category="x", severity="low", file="app/x.py", line=1,
                            message="made up", rule="FAKE-9"),
                ])
            return RunnableLambda(respond)

    monkeypatch.setattr(nodes, "get_llm", lambda: FakeLLM())
    state = {"diff": _diff('requests.get("http://billing.internal/x")'), "change_types": []}
    state["guidelines"] = nodes.retrieve_guidelines(state)["guidelines"]
    out = nodes._llm_review("security", state)
    assert "SEC-6" in seen["prompt"] and "internal_client" in seen["prompt"]
    assert [f.rule for f in out] == ["SEC-6", None]
    assert all(f.category == "security" for f in out)