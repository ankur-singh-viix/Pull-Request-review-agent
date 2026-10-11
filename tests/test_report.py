from evals.report import summarise


def test_summarise_counts_per_tier_and_overall():
    rows = [
        {"tier": "easy", "expected": ["bug"], "got": ["bug"]},
        {"tier": "easy", "expected": [], "got": ["style"]},
        {"tier": "hard", "expected": ["security"], "got": ["bug"]},
        {"tier": "hard", "expected": [], "got": []},
        {"id": "x", "error": "boom"},
    ]
    t = summarise(rows)
    assert t["easy"] == {"cases": 2, "tp": 1, "fn": 0, "fp": 1, "clean": 1, "flagged": 1}
    assert t["hard"] == {"cases": 2, "tp": 0, "fn": 1, "fp": 1, "clean": 1, "flagged": 0}
    assert t["all"]["cases"] == 4 and t["all"]["tp"] == 1