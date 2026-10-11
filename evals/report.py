"""Summarise a saved eval report per tier without calling any model.

  python -m evals.report evals/results/gemini_all.json
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def summarise(rows: list[dict]) -> dict[str, dict]:
    tiers: dict[str, dict] = defaultdict(
        lambda: {"cases": 0, "tp": 0, "fn": 0, "fp": 0, "clean": 0, "flagged": 0})
    for r in rows:
        if "error" in r:
            continue
        want, got = set(r["expected"]), set(r["got"])
        for key in (r["tier"], "all"):
            t = tiers[key]
            t["cases"] += 1
            t["tp"] += len(want & got)
            t["fn"] += len(want - got)
            t["fp"] += len(got - want)
            if not want:
                t["clean"] += 1
                t["flagged"] += bool(got)
    return dict(tiers)


def main(path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"{path}\nmode: {data.get('mode')}\n")
    print(f"{'tier':<6} {'cases':>5} {'recall':>7} {'precision':>9} {'clean flagged':>14}")
    tiers = summarise(data["cases"])
    for name in [t for t in ("easy", "hard", "team", "all") if t in tiers]:
        t = tiers[name]
        recall = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else 1.0
        precision = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else 1.0
        print(f"{name:<6} {t['cases']:>5} {recall:>7.2f} {precision:>9.2f} "
              f"{t['flagged']:>9}/{t['clean']}")


if __name__ == "__main__":
    main(sys.argv[1])