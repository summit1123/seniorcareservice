"""Run the full demo model pipeline in dependency order."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.features.build_model_features import build_model_features
from src.models.pattern_model import build_pattern_scores
from src.models.score_rules import build_score_table
from src.product.decision_rules import build_decision_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full senior care driving model pipeline.")
    parser.add_argument(
        "--input",
        default="data/raw/trip_sample.csv",
        help="Standardized trip CSV path. Use validate_trip_csv_mapping.py first for raw public CSVs.",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    feature_outputs = build_model_features(input_path=input_path)
    pattern_scores = build_pattern_scores()
    score_rows = build_score_table()
    decision_rows = build_decision_table()

    print(f"input: {input_path}")
    print("feature outputs")
    for name, path in feature_outputs.items():
        print(f"- {name}: {path}")
    print(f"pattern rows: {len(pattern_scores)}")
    print(f"score rows: {len(score_rows)}")
    print(f"decision rows: {len(decision_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
