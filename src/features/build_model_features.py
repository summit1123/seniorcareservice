"""Build the model feature table from trip data."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.data.load_trips import load_trips
from src.features.driving_features import aggregate_baseline_behavior, aggregate_recent_behavior
from src.features.zone_features import add_zone_features


ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "trip_sample.csv"
PROCESSED_DIR = ROOT / "data" / "processed"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        fieldnames = fieldnames or []
    else:
        fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def select_trip_feature_rows(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = [
        "driver_id",
        "trip_id",
        "period",
        "trip_start_time",
        "trip_distance_km",
        "night_flag",
        "start_grid",
        "end_grid",
        "in_zone_flag",
        "out_zone_flag",
        "route_repeat_flag",
        "new_destination_flag",
        "speeding_count",
        "harsh_accel_count",
        "harsh_brake_count",
        "sharp_turn_count",
    ]
    return [{field: row[field] for field in fields} for row in trips]


def merge_feature_tables(
    zone_rows: list[dict[str, Any]],
    driving_rows: list[dict[str, Any]],
    baseline_rows: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    zone_by_driver = {row["driver_id"]: row for row in zone_rows}
    result: list[dict[str, Any]] = []
    for driving in driving_rows:
        driver_id = driving["driver_id"]
        zone = zone_by_driver.get(driver_id, {})
        baseline = baseline_rows.get(driver_id, {})
        row = {**driving, **zone}
        row["out_zone_ratio_delta"] = round(row.get("out_zone_ratio", 0.0) - baseline.get("baseline_out_zone_ratio", 0.0), 4)
        row["speeding_delta_per_100km"] = round(
            row.get("speeding_per_100km", 0.0) - baseline.get("baseline_speeding_per_100km", 0.0),
            4,
        )
        row["harsh_brake_delta_per_100km"] = round(
            row.get("harsh_brake_per_100km", 0.0) - baseline.get("baseline_harsh_brake_per_100km", 0.0),
            4,
        )
        row["night_ratio_delta"] = round(row.get("night_ratio", 0.0) - baseline.get("baseline_night_ratio", 0.0), 4)
        result.append(row)
    return result


def build_model_features(input_path: Path = RAW_PATH, output_dir: Path = PROCESSED_DIR) -> dict[str, Path]:
    trips = load_trips(input_path)
    labeled_trips, zone_rows = add_zone_features(trips)
    driving_rows = aggregate_recent_behavior(labeled_trips)
    baseline_rows = aggregate_baseline_behavior(labeled_trips)
    model_rows = merge_feature_tables(zone_rows, driving_rows, baseline_rows)

    outputs = {
        "trip_feature_table": output_dir / "trip_feature_table.csv",
        "zone_feature_table": output_dir / "zone_feature_table.csv",
        "driving_feature_table": output_dir / "driving_feature_table.csv",
        "model_feature_table": output_dir / "model_feature_table.csv",
    }
    write_csv(outputs["trip_feature_table"], select_trip_feature_rows(labeled_trips))
    write_csv(outputs["zone_feature_table"], zone_rows)
    write_csv(outputs["driving_feature_table"], driving_rows)
    write_csv(outputs["model_feature_table"], model_rows)
    return outputs


def main() -> int:
    outputs = build_model_features()
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
