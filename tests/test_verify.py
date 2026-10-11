from langchain_core.runnables import RunnableLambda

from app import nodes
from app.state import Finding, Verdict


def _f(msg: str, conf: float = 0.9, verified: bool = False, line: int = 1) -> Finding:
    return Finding(category="bug", severity="medium", file="a.py", line=line, message=msg,
                   confidence=conf, verified=verified)


class SkepticLLM:
    """Rejects any finding whose text contains 'nitpick'."""

    def with_structured_output(self, schema):
        def respond(prompt_value):
            bad = "nitpick" in prompt_value.to_string()
            return Verdict(valid=not bad, confidence=0.1 if bad else 0.9)
        return RunnableLambda(respond)


def test_verified_verdict_beats_unverified_duplicate():
    state = {"findings": [_f("x", 0.9), _f("x", 0.0, verified=True)]}
    out = nodes.aggregate(state)
    assert out["final_findings"] == [] and out["pending"] == []


def test_offline_mode_does_not_verify_everything():
    out = nodes.aggregate({"findings": [_f("solid", 0.9)]})
    assert [f.message for f in out["final_findings"]] == ["solid"] and out["pending"] == []


def test_verify_all_drops_findings_the_skeptic_rejects(monkeypatch):
    monkeypatch.setattr(nodes, "use_fake", lambda: False)
    monkeypatch.setattr(nodes, "get_llm", lambda: SkepticLLM())
    monkeypatch.setenv("VERIFY_ALL", "1")
    state = {"diff": "+x", "findings": [_f("real bug", line=1), _f("a nitpick", line=2)]}

    first = nodes.aggregate(state)
    assert first["final_findings"] == [] and len(first["pending"]) == 2
    assert nodes.after_aggregate({**first, "verify_attempts": 0}) == "verify"

    state["pending"] = first["pending"]
    verified = nodes.verify(state)
    state["findings"] = state["findings"] + verified["findings"]
    final = nodes.aggregate(state)
    assert [f.message for f in final["final_findings"]] == ["real bug"]
    assert final["pending"] == []
    assert nodes.after_aggregate({**final, "verify_attempts": 1}) == "publish"


def test_verify_all_is_off_by_default(monkeypatch):
    monkeypatch.setattr(nodes, "use_fake", lambda: False)
    monkeypatch.delenv("VERIFY_ALL", raising=False)
    out = nodes.aggregate({"findings": [_f("solid", 0.9)]})
    assert [f.message for f in out["final_findings"]] == ["solid"] and out["pending"] == []

def test_one_finding_per_line_across_categories():
    def dup(category, severity, rule=None):
        return Finding(category=category, severity=severity, file="a.py", line=3,
                       message=f"{category} copy", confidence=1.0, rule=rule)

    # same line reported three ways: the finding that cites a team rule wins
    out = nodes.aggregate({"findings": [dup("bug", "high"), dup("style", "high"),
                                        dup("security", "high", rule="SEC-3")]})
    assert [(f.category, f.rule) for f in out["final_findings"]] == [("security", "SEC-3")]

    # no rules: higher severity wins, then category priority (bug before style)
    out = nodes.aggregate({"findings": [dup("style", "high"), dup("bug", "high"),
                                        dup("security", "low")]})
    assert [f.category for f in out["final_findings"]] == ["bug"]

    # findings without a line are kept per category
    out = nodes.aggregate({"findings": [
        Finding(category="tests", severity="medium", file="a.py", message="t", confidence=0.9),
        Finding(category="bug", severity="medium", file="a.py", message="b", confidence=0.9)]})
    assert len(out["final_findings"]) == 2