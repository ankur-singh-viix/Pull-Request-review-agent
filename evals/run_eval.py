"""Eval gate. Exits non-zero if recall/precision fall below thresholds.

  python -m evals.run_eval --min-recall 0.8 --min-precision 0.8
Runs offline (heuristics) unless an API key is set and USE_FAKE_LLM != 1.
"""
import argparse
import json
import sys
from pathlib import Path

from app.graph import run_review

DATA = Path(__file__).parent / "dataset.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-recall", type=float, default=0.8)
    ap.add_argument("--min-precision", type=float, default=0.8)
    args = ap.parse_args()

    tp = fn = fp = 0
    for case in json.loads(DATA.read_text()):
        got = {f.category for f in run_review(diff=case["diff"])["final_findings"]}
        want = set(case["expected"])
        tp += len(got & want)
        fn += len(want - got)
        fp += len(got - want)
        status = "ok " if got == want else "MISS"
        print(f"[{status}] {case['id']:<20} expected={sorted(want)} got={sorted(got)}")

    recall = tp / (tp + fn) if tp + fn else 1.0
    precision = tp / (tp + fp) if tp + fp else 1.0
    print(f"\nrecall={recall:.2f} precision={precision:.2f}")
    if recall < args.min_recall or precision < args.min_precision:
        print("EVAL GATE FAILED")
        return 1
    print("EVAL GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
