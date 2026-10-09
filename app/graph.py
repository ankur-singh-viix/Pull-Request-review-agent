from langgraph.graph import END, START, StateGraph

from app import heuristics
from app.nodes import after_aggregate, aggregate, fetch, make_reviewer, publish, router, verify
from app.state import ReviewState

REVIEWERS = {
    "security": heuristics.review_security,
    "bugs": heuristics.review_bugs,
    "style": heuristics.review_style,
    "test_coverage": heuristics.review_tests,
}
CATEGORY = {"security": "security", "bugs": "bug", "style": "style", "test_coverage": "tests"}


def build_graph():
    g = StateGraph(ReviewState)
    g.add_node("fetch", fetch)
    g.add_node("router", router)
    for name, h in REVIEWERS.items():
        g.add_node(name, make_reviewer(CATEGORY[name], h))
    g.add_node("aggregate", aggregate)
    g.add_node("verify", verify)
    g.add_node("publish", publish)

    g.add_edge(START, "fetch")
    g.add_edge("fetch", "router")
    for name in REVIEWERS:          # fan-out: reviewers run in parallel
        g.add_edge("router", name)
    g.add_edge(list(REVIEWERS), "aggregate")   # fan-in: wait for all reviewers
    g.add_conditional_edges("aggregate", after_aggregate, {"verify": "verify", "publish": "publish"})
    g.add_edge("verify", "aggregate")          # retry loop
    g.add_edge("publish", END)
    return g.compile()


graph = build_graph()


def run_review(repo: str = "", pr_number: int = 0, diff: str = "") -> dict:
    return graph.invoke({"repo": repo, "pr_number": pr_number, "diff": diff})
