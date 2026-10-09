from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .ablation import evaluate_ablations
from .evaluate import evaluate_all
from .features import build_features
from .schema import validate_observations
from .simulator import DEFAULT_SCENARIOS, simulate_dataset


def _config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _write_features(raw: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    raw = validate_observations(raw)
    features = build_features(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out_dir / "observations.csv", index=False)
    features.to_csv(out_dir / "features.csv", index=False)
    return features


def _generate(cfg: dict, out_dir: Path) -> pd.DataFrame:
    seeds = range(int(cfg["dataset"]["seeds"]))
    steps = int(cfg["dataset"]["steps"])
    raw = simulate_dataset(DEFAULT_SCENARIOS, seeds=seeds, steps=steps)
    return _write_features(raw, out_dir)


def _ingest(path: str, out_dir: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    return _write_features(raw, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NFStatusNotify distributed-state consistency research harness"
    )
    parser.add_argument(
        "command",
        choices=("generate", "ingest", "evaluate", "ablate", "all"),
        nargs="?",
        default="all",
    )
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--out", default="artifacts")
    parser.add_argument(
        "--observations",
        help="CSV following the Open5GS telemetry adapter contract; used by 'ingest'",
    )
    args = parser.parse_args()

    cfg = _config(args.config)
    out_dir = Path(args.out)
    features_path = out_dir / "features.csv"

    if args.command in {"generate", "all"}:
        features = _generate(cfg, out_dir)
    elif args.command == "ingest":
        if not args.observations:
            raise SystemExit("'ingest' requires --observations path/to/observations.csv")
        features = _ingest(args.observations, out_dir)
        print(f"validated {len(features)} observations; wrote {features_path}")
    else:
        if not features_path.exists():
            raise SystemExit(
                f"{features_path} does not exist; run 'generate' or 'ingest' first"
            )
        features = pd.read_csv(features_path)

    target_fpr = float(cfg["evaluation"]["target_fpr"])
    random_state = int(cfg["evaluation"]["random_state"])

    if args.command in {"evaluate", "all"}:
        metrics = evaluate_all(
            features, target_fpr=target_fpr, random_state=random_state
        )
        metrics.to_csv(out_dir / "metrics.csv", index=False)
        print(metrics.to_string(index=False))

    if args.command in {"ablate", "all"}:
        ablations = evaluate_ablations(features, target_fpr=target_fpr)
        ablations.to_csv(out_dir / "ablations.csv", index=False)
        print(ablations.to_string(index=False))


if __name__ == "__main__":
    main()
