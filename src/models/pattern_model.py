"""Pattern-change anomaly scoring for the proposal demo.

The model compares recent trip vectors with each driver's baseline vectors and
keeps the strongest positive change signal so the report can explain why a
customer was separated for reward, default monitoring, or preventive care.
"""

from __future__ import annotations

import csv
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from src.features.build_model_features import write_csv


ROOT = Path(__file__).resolve().parents[2]
TRIP_FEATURE_PATH = ROOT / "data" / "processed" / "trip_feature_table.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "pattern_change_score.csv"

FEATURE_WEIGHTS = {
    "trip_distance_km": 0.8,
    "out_zone_flag": 1.4,
    "night_flag": 1.0,
    "speeding_per_100km": 1.6,
    "harsh_brake_per_100km": 1.4,
    "sharp_turn_per_100km": 1.0,
}

FEATURE_LABELS = {
    "trip_distance_km": "trip_distance_increase",
    "out_zone_flag": "out_zone_increase",
    "night_flag": "night_driving_increase",
    "speeding_per_100km": "speeding_increase",
    "harsh_brake_per_100km": "harsh_brake_increase",
    "sharp_turn_per_100km": "sharp_turn_increase",
}

MIN_SCALES = {
    "trip_distance_km": 4.0,
    "out_zone_flag": 0.25,
    "night_flag": 0.20,
    "speeding_per_100km": 3.0,
    "harsh_brake_per_100km": 3.0,
    "sharp_turn_per_100km": 3.0,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def trip_vector(row: dict[str, str]) -> dict[str, float]:
    distance = float(row["trip_distance_km"])
    safe_distance = max(distance, 0.1)
    return {
        "trip_distance_km": distance,
        "out_zone_flag": float(row["out_zone_flag"]),
        "night_flag": 1.0 if row["night_flag"] in {"True", "1", "true"} else 0.0,
        "speeding_per_100km": float(row["speeding_count"]) / safe_distance * 100,
        "harsh_brake_per_100km": float(row["harsh_brake_count"]) / safe_distance * 100,
        "sharp_turn_per_100km": float(row["sharp_turn_count"]) / safe_distance * 100,
    }


def baseline_stats(vectors: list[dict[str, float]]) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for feature in FEATURE_WEIGHTS:
        values = [vector[feature] for vector in vectors]
        avg = mean(values) if values else 0.0
        std = pstdev(values) if len(values) > 1 else 0.0
        stats[feature] = (avg, max(std, MIN_SCALES[feature]))
    return stats


def score_recent_vectors(
    recent: list[dict[str, float]],
    stats: dict[str, tuple[float, float]],
) -> tuple[float, str, float]:
    if not recent:
        return 0.0, "no_recent_trip", 0.0

    trip_scores: list[float] = []
    feature_totals = {feature: 0.0 for feature in FEATURE_WEIGHTS}
    for vector in recent:
        weighted_distance = 0.0
        total_weight = 0.0
        for feature, weight in FEATURE_WEIGHTS.items():
            avg, scale = stats[feature]
            positive_delta = max(0.0, vector[feature] - avg)
            contribution = weight * (positive_delta / scale)
            feature_totals[feature] += contribution
            weighted_distance += contribution
            total_weight += weight
        trip_scores.append(weighted_distance / total_weight)

    top_feature = max(feature_totals, key=feature_totals.get)
    top_contribution = feature_totals[top_feature] / len(recent)
    return min(100.0, mean(trip_scores) * 85), FEATURE_LABELS[top_feature], top_contribution


def fallback_pattern_scores(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_driver: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_driver.setdefault(row["driver_id"], []).append(row)

    output: list[dict[str, Any]] = []
    for driver_id, driver_rows in sorted(by_driver.items()):
        baseline = [trip_vector(row) for row in driver_rows if row["period"] == "baseline"]
        recent = [trip_vector(row) for row in driver_rows if row["period"] == "recent"]
        if not baseline:
            output.append(
                {
                    "driver_id": driver_id,
                    "pattern_change_score": 0.0,
                    "anomaly_flag": 0,
                    "pattern_model_backend": "insufficient_baseline",
                    "top_change_signal": "no_baseline_trip",
                    "top_change_contribution": 0.0,
                }
            )
            continue
        stats = baseline_stats(baseline)
        score, top_signal, top_contribution = score_recent_vectors(recent, stats)
        output.append(
            {
                "driver_id": driver_id,
                "pattern_change_score": round(score, 2),
                "anomaly_flag": int(score >= 60),
                "pattern_model_backend": "baseline_distance_anomaly",
                "top_change_signal": top_signal,
                "top_change_contribution": round(top_contribution, 4),
            }
        )
    return output


def build_pattern_scores(input_path: Path = TRIP_FEATURE_PATH, output_path: Path = OUTPUT_PATH) -> list[dict[str, Any]]:
    rows = read_csv(input_path)
    scores = fallback_pattern_scores(rows)
    write_csv(output_path, scores)
    return scores


def main() -> int:
    scores = build_pattern_scores()
    print(f"pattern scores: {OUTPUT_PATH}")
    for row in scores:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
