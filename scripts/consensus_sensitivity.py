#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from nfnotify_lab.features import build_features
from nfnotify_lab.sensitivity import ConsensusGrid, evaluate_consensus_grid, pareto_frontier
from nfnotify_lab.simulator import DEFAULT_SCENARIOS, simulate_dataset


def _parse_steps(value: str) -> tuple[int, ...]:
    steps = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not steps:
        raise argparse.ArgumentTypeError("step list must not be empty")
    if any(step < 1 for step in steps):
        raise argparse.ArgumentTypeError("all persistence steps must be >= 1")
    return steps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seeds", type=int, default=60)
    parser.add_argument("--steps", type=int, default=90)
    parser.add_argument("--target-fpr", type=float, default=0.001)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--single", type=_parse_steps, default=(4, 6, 8, 10, 12, 16))
    parser.add_argument("--dual", type=_parse_steps, default=(1, 2, 3, 4))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    raw = simulate_dataset(
        DEFAULT_SCENARIOS,
        seeds=range(args.seeds),
        steps=args.steps,
    )
    features = build_features(raw)
    run_split, holdout = evaluate_consensus_grid(
        features,
        target_fpr=args.target_fpr,
        random_state=args.random_state,
        grid=ConsensusGrid(
            single_source_steps=tuple(args.single),
            dual_source_steps=tuple(args.dual),
        ),
    )
    frontier = pareto_frontier(holdout)

    raw.to_csv(out / "development-observations.csv", index=False)
    run_split.to_csv(out / "consensus-sensitivity-run-split.csv", index=False)
    holdout.to_csv(out / "consensus-sensitivity-scenario-holdout.csv", index=False)
    frontier.to_csv(out / "consensus-sensitivity-pareto.csv", index=False)

    reference = holdout.loc[holdout["is_reference_2_12"]].iloc[0].to_dict()
    target_ok = holdout.loc[holdout["unseen_scenario_fpr"] <= args.target_fpr]
    best_recall = (
        target_ok.sort_values(
            ["unseen_attack_recall", "median_attack_scenario_delay"],
            ascending=[False, True],
        ).iloc[0].to_dict()
        if len(target_ok)
        else None
    )

    summary = {
        "development_only": True,
        "real_test_used_for_selection": False,
        "seeds": args.seeds,
        "steps": args.steps,
        "target_fpr": args.target_fpr,
        "single_source_grid": list(args.single),
        "dual_source_grid": list(args.dual),
        "reference_2_12": reference,
        "best_recall_subject_to_target_fpr": best_recall,
        "pareto_points": int(len(frontier)),
    }
    (out / "consensus-sensitivity-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(holdout.to_string(index=False))


if __name__ == "__main__":
    main()
