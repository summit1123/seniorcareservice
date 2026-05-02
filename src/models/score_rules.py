"""Score calculation rules for the demo rider model."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.features.build_model_features import write_csv


ROOT = Path(__file__).resolve().parents[2]
MODEL_FEATURE_PATH = ROOT / "data" / "processed" / "model_feature_table.csv"
PATTERN_SCORE_PATH = ROOT / "data" / "processed" / "pattern_change_score.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "score_table.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csvfile:
        return list(csv.DictReader(csvfile))


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def calculate_safe_driving(row: dict[str, str]) -> float:
    penalty = (
        float(row["speeding_per_100km"]) * 4.0
        + float(row["harsh_accel_per_100km"]) * 2.5
        + float(row["harsh_brake_per_100km"]) * 3.0
        + float(row["sharp_turn_per_100km"]) * 2.0
        + float(row["night_ratio"]) * 15.0
    )
    return round(clamp(100 - penalty), 2)


def calculate_out_zone_risk(row: dict[str, str]) -> float:
    risk = (
        float(row["out_zone_ratio"]) * 35.0
        + max(0.0, float(row["out_zone_ratio_delta"])) * 30.0
        + float(row["speeding_per_100km"]) * 3.5
        + float(row["harsh_brake_per_100km"]) * 2.6
        + float(row["night_ratio"]) * 20.0
        + max(0.0, float(row["night_ratio_delta"])) * 15.0
    )
    return round(clamp(risk), 2)


def build_score_table(
    model_feature_path: Path = MODEL_FEATURE_PATH,
    pattern_score_path: Path = PATTERN_SCORE_PATH,
    output_path: Path = OUTPUT_PATH,
) -> list[dict[str, Any]]:
    features = read_csv(model_feature_path)
    pattern_by_driver = {row["driver_id"]: row for row in read_csv(pattern_score_path)}

    rows: list[dict[str, Any]] = []
    for feature in features:
        driver_id = feature["driver_id"]
        pattern = pattern_by_driver.get(driver_id, {})
        pattern_change_score = float(pattern.get("pattern_change_score", 0.0))
        safe_driving_score = calculate_safe_driving(feature)
        familiar_zone_score = float(feature["zone_stability_score"])
        out_zone_behavior_risk = calculate_out_zone_risk(feature)
        care_trigger_score = round(
            clamp(pattern_change_score * 0.45 + out_zone_behavior_risk * 0.35 + (100 - safe_driving_score) * 0.20),
            2,
        )
        rows.append(
            {
                "driver_id": driver_id,
                "safe_driving_score": safe_driving_score,
                "familiar_zone_score": familiar_zone_score,
                "pattern_change_score": pattern_change_score,
                "out_zone_behavior_risk": out_zone_behavior_risk,
                "care_trigger_score": care_trigger_score,
            }
        )

    write_csv(output_path, rows)
    return rows


def main() -> int:
    rows = build_score_table()
    print(f"score table: {OUTPUT_PATH}")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
