"""Eval gate: scores the reviewer on labeled diffs and fails if quality drops.

  python -m evals.run_eval --tier easy --min-recall 0.8 --min-precision 0.8   # offline CI gate
  python -m evals.run_eval --tier all --save evals/results/live.json          # live model

Runs with the offline heuristics when no API key is set (or USE_FAKE_LLM=1).
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.graph import run_review
from app.llm import describe
from app.rag import guidelines_enabled
from evals.cases import CASES


def _rates(tp: int, fn: int, fp: int) -> tuple[float, float]:
    recall = tp / (tp + fn) if tp + fn else 1.0
    precision = tp / (tp + fp) if tp + fp else 1.0
    return recall, precision


def evaluate(cases: list[dict]) -> dict:
    per: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
    rows: list[dict] = []
    clean_total = clean_flagged = errors = 0

    for case in cases:
        want = set(case["expected"])
        start = time.perf_counter()
        try:
            out = run_review(diff=case["diff"])
        except Exception as exc:  # noqa: BLE001  (network, rate-limit, parsing errors)
            errors += 1
            rows.append({"id": case["id"], "error": str(exc)[:200]})
            print(f"[ERR ] {case['id']:<28} {type(exc).__name__}: {str(exc)[:70]}")
            continue
        got = {f.category for f in out["final_findings"]}
        for cat in got | want:
            if cat in got and cat in want:
                per[cat]["tp"] += 1
            elif cat in want:
                per[cat]["fn"] += 1
            else:
                per[cat]["fp"] += 1
        if not want:
            clean_total += 1
            clean_flagged += bool(got)
        secs = time.perf_counter() - start
        rows.append({"id": case["id"], "tier": case["tier"], "expected": sorted(want),
                     "got": sorted(got), "seconds": round(secs, 2)})
        status = "ok  " if got == want else "MISS"
        print(f"[{status}] {case['id']:<28} expected={sorted(want)} got={sorted(got)} "
              f"({secs:.1f}s)")

    tp = sum(v["tp"] for v in per.values())
    fn = sum(v["fn"] for v in per.values())
    fp = sum(v["fp"] for v in per.values())
    recall, precision = _rates(tp, fn, fp)
    return {
        "recall": recall, "precision": precision, "errors": errors,
        "false_positive_rate_on_clean": clean_flagged / clean_total if clean_total else 0.0,
        "per_category": {c: dict(zip(("recall", "precision"), _rates(**v), strict=True))
                         for c, v in sorted(per.items())},
        "cases": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["easy", "hard","team", "all"], default="all")
    ap.add_argument("--min-recall", type=float, default=0.0)
    ap.add_argument("--min-precision", type=float, default=0.0)
    ap.add_argument("--save", help="write a JSON report to this path")
    args = ap.parse_args()

    cases = [c for c in CASES if args.tier == "all" or c["tier"] == args.tier]
    mode = f"{describe()} rag={'on' if guidelines_enabled() else 'off'}"
    print(f"mode={mode} tier={args.tier} cases={len(cases)}\n")
    report = evaluate(cases)

    print("\nper category:")
    for cat, m in report["per_category"].items():
        print(f"  {cat:<9} recall={m['recall']:.2f} precision={m['precision']:.2f}")
    print(f"\nOVERALL recall={report['recall']:.2f} precision={report['precision']:.2f} "
          f"false-positive-rate-on-clean={report['false_positive_rate_on_clean']:.2f} "
          f"errors={report['errors']}")

    if args.save:
        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mode": mode, "tier": args.tier, **report}, indent=2))
        print(f"saved {path}")

    if report["errors"]:
        print("EVAL ERRORED (some cases could not run)")
        return 2
    if report["recall"] < args.min_recall or report["precision"] < args.min_precision:
        print("EVAL GATE FAILED")
        return 1
    print("EVAL GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())