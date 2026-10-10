from app.heuristics import added_lines
from evals.cases import CASES
from evals.run_eval import evaluate

CATEGORIES = {"security", "bug", "style", "tests"}


def test_cases_are_well_formed():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for c in CASES:
        assert c["tier"] in {"easy", "hard" , "team", "all"}
        assert set(c["expected"]) <= CATEGORIES
        assert list(added_lines(c["diff"])), c["id"]


def test_easy_tier_passes_offline_gate():
    report = evaluate([c for c in CASES if c["tier"] == "easy"])
    assert report["recall"] >= 0.8 and report["precision"] >= 0.8
    assert report["errors"] == 0