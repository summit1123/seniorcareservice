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

DEFAULT_SENIOR_SAFE_MILEAGE_WEIGHTS = {
    "w_mileage": 0.35,
    "w_in_zone": 0.35,
    "w_out_zone_safe": 0.15,
    "w_out_zone_change": 0.15,
}

P90_THRESHOLD_FIELDS = (
    "zone_buffer_m",
    "living_zone_departure_p90_raw_m",
    "living_zone_departure_p90_threshold_m",
    "living_zone_departure_threshold_sample_count",
    "living_zone_departure_threshold_percentile",
    "baseline_trip_distance_p90_km",
    "baseline_trip_distance_threshold_sample_count",
    "baseline_trip_distance_threshold_percentile",
    "baseline_movement_frequency_p90_per_day",
    "baseline_movement_frequency_threshold_sample_count",
    "baseline_movement_frequency_threshold_percentile",
    "primary_zone_p90_radius_m",
)

OUTSIDE_LIVING_ZONE_SEGMENT_FIELDS = (
    "living_zone_outside_segment_criteria",
    "living_zone_outside_segment_count",
    "living_zone_outside_segment_ratio",
    "living_zone_outside_segment_km",
    "living_zone_outside_segment_distance_ratio",
    "living_zone_outside_segment_night_ratio",
    "living_zone_outside_segment_speeding_count",
    "living_zone_outside_segment_harsh_accel_count",
    "living_zone_outside_segment_harsh_brake_count",
    "living_zone_outside_segment_sharp_turn_count",
    "living_zone_outside_segment_risk_event_count",
    "living_zone_outside_segment_speeding_per_100km",
    "living_zone_outside_segment_harsh_accel_per_100km",
    "living_zone_outside_segment_harsh_brake_per_100km",
    "living_zone_outside_segment_sharp_turn_per_100km",
    "living_zone_outside_segment_risk_events_per_100km",
    "baseline_living_zone_outside_segment_count",
    "baseline_living_zone_outside_segment_ratio",
    "baseline_living_zone_outside_segment_km",
    "baseline_living_zone_outside_segment_distance_ratio",
    "baseline_living_zone_outside_segment_risk_events_per_100km",
    "baseline_living_zone_outside_segment_night_ratio",
    "living_zone_outside_segment_ratio_delta",
    "living_zone_outside_segment_distance_ratio_delta",
    "living_zone_outside_segment_risk_events_delta_per_100km",
    "living_zone_outside_segment_night_ratio_delta",
    "living_zone_outside_segment_risk_change_score",
)


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


def calculate_in_zone_safe_driving(row: dict[str, str]) -> float:
    """Score safe-driving behavior on core/buffer living-zone segments."""
    if "in_zone_total_km" not in row or float(row.get("in_zone_total_km") or 0.0) <= 0:
        return calculate_safe_driving(row)
    penalty = (
        float(row.get("in_zone_speeding_per_100km") or 0.0) * 4.0
        + float(row.get("in_zone_harsh_accel_per_100km") or 0.0) * 2.5
        + float(row.get("in_zone_harsh_brake_per_100km") or 0.0) * 3.0
        + float(row.get("in_zone_sharp_turn_per_100km") or 0.0) * 2.0
        + float(row.get("in_zone_night_ratio") or 0.0) * 15.0
    )
    return round(clamp(100 - penalty), 2)


def calculate_out_zone_safe_driving(row: dict[str, str]) -> float:
    """Score safe-driving behavior only on DBSCAN/P90 outside living-zone segments."""
    outside_km = float(row.get("living_zone_outside_segment_km") or 0.0)
    outside_count = int(float(row.get("living_zone_outside_segment_count") or 0))
    if outside_km <= 0 or outside_count <= 0:
        return 100.0

    penalty = (
        float(row.get("living_zone_outside_segment_speeding_per_100km") or 0.0) * 4.0
        + float(row.get("living_zone_outside_segment_harsh_accel_per_100km") or 0.0) * 2.5
        + float(row.get("living_zone_outside_segment_harsh_brake_per_100km") or 0.0) * 3.0
        + float(row.get("living_zone_outside_segment_sharp_turn_per_100km") or 0.0) * 2.0
    )
    return round(clamp(100 - penalty), 2)


def calculate_out_zone_risk(row: dict[str, str]) -> float:
    outside_risk_events = float(row.get("living_zone_outside_segment_risk_events_per_100km") or 0.0)
    outside_harsh_brake = float(row.get("living_zone_outside_segment_harsh_brake_per_100km") or 0.0)
    outside_change_score = float(row.get("living_zone_outside_segment_risk_change_score") or 0.0)
    outside_distance_ratio_delta = max(
        0.0,
        float(row.get("living_zone_outside_segment_distance_ratio_delta") or 0.0),
    )
    outside_risk_events_delta = max(
        0.0,
        float(row.get("living_zone_outside_segment_risk_events_delta_per_100km") or 0.0),
    )
    outside_night_ratio_delta = max(
        0.0,
        float(row.get("living_zone_outside_segment_night_ratio_delta") or 0.0),
    )
    risk = (
        float(row["out_zone_ratio"]) * 35.0
        + max(0.0, float(row["out_zone_ratio_delta"])) * 30.0
        + outside_risk_events * 2.0
        + outside_harsh_brake * 2.6
        + float(row["night_ratio"]) * 20.0
        + max(0.0, float(row["night_ratio_delta"])) * 15.0
        + outside_change_score * 0.25
        + outside_distance_ratio_delta * 15.0
        + outside_risk_events_delta * 1.5
        + outside_night_ratio_delta * 12.0
    )
    return round(clamp(risk), 2)


def calculate_mileage_baseline_score(row: dict[str, str]) -> float:
    annualized_km = float(row.get("annualized_recent_km") or 0.0)
    if annualized_km <= 0:
        annualized_km = float(row.get("total_km") or 0.0) * 12.0
    return round(clamp(100.0 - (annualized_km / 12_000.0 * 100.0)), 2)


def calculate_senior_safe_mileage_score(
    row: dict[str, str],
    weights: dict[str, float] | None = None,
) -> float:
    """Calculate the integrated score with DBSCAN/P90 outside-zone risk-change input."""
    selected_weights = weights or DEFAULT_SENIOR_SAFE_MILEAGE_WEIGHTS
    mileage_baseline_score = calculate_mileage_baseline_score(row)
    in_zone_safe_score = calculate_in_zone_safe_driving(row)
    out_zone_safe_score = calculate_out_zone_safe_driving(row)
    out_zone_change_risk = calculate_out_zone_risk(row)
    score = (
        mileage_baseline_score * selected_weights["w_mileage"]
        + in_zone_safe_score * selected_weights["w_in_zone"]
        + out_zone_safe_score * selected_weights["w_out_zone_safe"]
        + (100.0 - out_zone_change_risk) * selected_weights["w_out_zone_change"]
    )
    return round(clamp(score), 2)


def p90_threshold_snapshot(row: dict[str, str]) -> dict[str, float | int | str]:
    """Return customer-level P90 thresholds for scoring, decisions, and UI display."""
    snapshot: dict[str, float | int | str] = {}
    for field in P90_THRESHOLD_FIELDS:
        value = row.get(field, "")
        if value == "":
            snapshot[field] = ""
            continue
        if field.endswith("_sample_count"):
            snapshot[field] = int(float(value))
        else:
            snapshot[field] = round(float(value), 4)
    return snapshot


def outside_living_zone_segment_snapshot(row: dict[str, str]) -> dict[str, float | int | str]:
    """Return decision/model fields describing trips outside the living-zone threshold."""
    snapshot: dict[str, float | int | str] = {
        "living_zone_outside_segment_criteria": row.get("living_zone_outside_segment_criteria", ""),
        "living_zone_outside_segment_count": int(float(row.get("living_zone_outside_segment_count") or 0)),
        "living_zone_outside_segment_ratio": round(float(row.get("living_zone_outside_segment_ratio") or 0.0), 4),
        "living_zone_outside_segment_km": round(float(row.get("living_zone_outside_segment_km") or 0.0), 2),
        "living_zone_outside_segment_distance_ratio": round(
            float(row.get("living_zone_outside_segment_distance_ratio") or 0.0),
            4,
        ),
        "living_zone_outside_segment_night_ratio": round(
            float(row.get("living_zone_outside_segment_night_ratio") or 0.0),
            4,
        ),
    }
    for field in OUTSIDE_LIVING_ZONE_SEGMENT_FIELDS:
        if field in snapshot or field == "living_zone_outside_segment_criteria":
            continue
        if field.endswith("_count"):
            snapshot[field] = int(float(row.get(field) or 0))
        else:
            snapshot[field] = round(float(row.get(field) or 0.0), 4)
    return snapshot


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
        overall_safe_driving_score = calculate_safe_driving(feature)
        in_zone_safe_score = calculate_in_zone_safe_driving(feature)
        out_zone_safe_score = calculate_out_zone_safe_driving(feature)
        safe_driving_score = round(
            clamp(in_zone_safe_score * 0.55 + out_zone_safe_score * 0.25 + overall_safe_driving_score * 0.20),
            2,
        )
        familiar_zone_score = float(feature["zone_stability_score"])
        out_zone_behavior_risk = calculate_out_zone_risk(feature)
        mileage_baseline_score = calculate_mileage_baseline_score(feature)
        senior_safe_mileage_score = calculate_senior_safe_mileage_score(feature)
        care_trigger_score = round(
            clamp(pattern_change_score * 0.45 + out_zone_behavior_risk * 0.35 + (100 - safe_driving_score) * 0.20),
            2,
        )
        rows.append(
            {
                "customer_id": feature.get("customer_id", driver_id),
                "driver_id": driver_id,
                "persona_type": feature.get("persona_type", ""),
                "safe_driving_score": safe_driving_score,
                "mileage_baseline_score": mileage_baseline_score,
                "senior_safe_mileage_score": senior_safe_mileage_score,
                "overall_safe_driving_score": overall_safe_driving_score,
                "in_zone_safe_score": in_zone_safe_score,
                "out_zone_safe_score": out_zone_safe_score,
                "in_zone_total_km": round(float(feature.get("in_zone_total_km") or 0.0), 2),
                "in_zone_trip_count": int(float(feature.get("in_zone_trip_count") or 0)),
                "in_zone_distance_ratio": round(float(feature.get("in_zone_distance_ratio") or 0.0), 4),
                "in_zone_risk_events_per_100km": round(
                    float(feature.get("in_zone_risk_events_per_100km") or 0.0),
                    4,
                ),
                "familiar_zone_score": familiar_zone_score,
                "pattern_change_score": pattern_change_score,
                "risk_change_score": out_zone_behavior_risk,
                "out_zone_behavior_risk": out_zone_behavior_risk,
                "care_trigger_score": care_trigger_score,
                **p90_threshold_snapshot(feature),
                **outside_living_zone_segment_snapshot(feature),
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
