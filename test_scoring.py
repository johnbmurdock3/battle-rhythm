"""Offline verification: run the ACTUAL score()/scoring_diff() from sleeper_client
against stat lines and ground-truth points captured live from the Sleeper API.
Ground truth = players_points computed by Sleeper itself in league matchups.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from battle_rhythm.sleeper_client import score, scoring_diff

FIX = pathlib.Path(__file__).parent / "fixtures"


def main():
    data = json.loads((FIX / "verify_cases.json").read_text(encoding="utf-8"))
    failures = 0
    print("scoring dot-product verification (ground truth = Sleeper's players_points)\n")
    for case in data["cases"]:
        scoring = data[case["scoring"]]
        got = score(case["stats"], scoring)
        ok = abs(got - case["expected"]) < 0.005
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  computed {got:>7.2f}  sleeper {case['expected']:>7.2f}  {case['label']}")

    lg = json.loads((FIX / "leagues_2026_scoring.json").read_text(encoding="utf-8"))["leagues"]
    print("\nwhere the five 2026 leagues disagree on scoring")
    hdr = [l["name"].strip()[:14] for l in lg]
    print(f"  {'rule':<18}" + "".join(f"{h:>16}" for h in hdr))
    for k, vals in scoring_diff(lg).items():
        print(f"  {k:<18}" + "".join(f"{v:>16g}" for v in vals))

    print(f"\n{'ALL PASS' if not failures else f'{failures} FAILURES'}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
